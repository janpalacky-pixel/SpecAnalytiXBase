
# src/modules/data_analysis/spectral_range_manager.py

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.stats import binned_statistic
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history

logger = get_logger(__name__)

class SpectralRangeManager:
    """Business logic for managing spectral ranges and processing spectra."""
    
    def __init__(self):
        self.spectrum_ranges = {}  # Dictionary to store ranges for each spectrum
        self.spectrum_exclude_modes = {}  # Dictionary to store exclude mode for each spectrum
        self.spectrum_x_steps = {}  # Dictionary to store linearization step for each spectrum
        self.spectrum_x_mins = {}  # Dictionary to store x_min for each spectrum
        self.spectrum_x_maxs = {}  # Dictionary to store x_max for each spectrum
        self.current_ranges = []  # Current ranges shown in dialog
        self.is_exclude_mode = False  # Current exclude mode in dialog — Include is the more intuitive default
        self.x_step = 1.0
        self.x_min = None  # Current active x_min value
        self.x_max = None  # Current active x_max value
        self.apply_linearization = False

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum key for the settings dicts below — uses the
        spectrum's persistent unique_id rather than its label. Labels are
        not stable identifiers: renaming a spectrum doesn't change its
        identity, and two completely unrelated spectra (e.g. from separate
        import sessions, or a re-imported file producing the same
        filename-derived labels) can end up sharing a label even though
        they've never had anything to do with each other. Falls back to
        label only if a spectrum genuinely has no unique_id, which
        shouldn't normally happen."""
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum['label']

    @staticmethod
    def find_nearest_idx(array, value):
        """Find index of nearest value in array."""
        return (np.abs(array - value)).argmin()
    
    def _normalize_range(self, range_pair):
        """Normalize a range pair to always be [smaller, larger]."""
        start, end = range_pair
        return [min(start, end), max(start, end)]

    def _normalize_ranges(self, ranges):
        """Normalize and sort ranges for comparison."""
        # Normalize each range
        normalized = [self._normalize_range(r) for r in ranges]
        # Sort ranges by their start value
        return sorted(normalized, key=lambda x: (x[0], x[1]))

    def _ranges_equal(self, ranges1, ranges2):
        """Compare two sets of ranges, ignoring order."""
        if len(ranges1) != len(ranges2):
            return False
        norm1 = self._normalize_ranges(ranges1)
        norm2 = self._normalize_ranges(ranges2)
        return all(r1 == r2 for r1, r2 in zip(norm1, norm2))

    def prune_to_current_spectra(self, current_spectra):
        """Remove per-spectrum entries (ranges/modes/steps/limits) for any
        key not belonging to a spectrum in current_spectra. Without this,
        a spectrum that's gone (cleared, replaced by a new import) leaves
        its old settings behind forever, keyed by whatever identified it
        at the time."""
        current_keys = {self._key_for(s) for s in current_spectra}
        for d in (self.spectrum_ranges, self.spectrum_exclude_modes,
                  self.spectrum_x_steps, self.spectrum_x_mins, self.spectrum_x_maxs):
            for key in list(d.keys()):
                if key not in current_keys:
                    del d[key]

    def have_identical_settings(self, spectra):
        """
        Check if all selected spectra have identical settings.
        Returns tuple (identical_all: bool, 
                      identical_ranges: bool, common_ranges: list,
                      identical_modes: bool, common_mode: bool,
                      identical_steps: bool, common_step: float,
                      identical_limits: bool, common_x_min: float, common_x_max: float)
        """
        if not spectra or len(spectra) == 0:
            return False, False, [], False, False, False, 1.0, False, None, None
            
        # Collect settings from all spectra
        ranges_list = []
        modes_list = []
        steps_list = []
        x_mins_list = []
        x_maxs_list = []
        
        for spectrum in spectra:
            key = self._key_for(spectrum)
            ranges = self.spectrum_ranges.get(key, [])
            # Normalize ranges before comparison
            ranges = self._normalize_ranges(ranges)
            mode = self.spectrum_exclude_modes.get(key, False)
            step = self.spectrum_x_steps.get(key, 1.0)
            x_min = self.spectrum_x_mins.get(key)
            x_max = self.spectrum_x_maxs.get(key)
            
            ranges_list.append(tuple(map(tuple, ranges)))
            modes_list.append(mode)
            steps_list.append(step)
            x_mins_list.append(x_min)
            x_maxs_list.append(x_max)
            
        # Get first spectrum's settings
        first_ranges = ranges_list[0] if ranges_list else ()
        first_mode = modes_list[0] if modes_list else False
        first_step = steps_list[0] if steps_list else 1.0
        first_x_min = x_mins_list[0]
        first_x_max = x_maxs_list[0]
        
        # Check if all spectra have the same settings
        identical_ranges = all(ranges == first_ranges for ranges in ranges_list)
        identical_modes = all(mode == first_mode for mode in modes_list)
        identical_steps = all(step == first_step for step in steps_list)
        identical_limits = (all(x_min == first_x_min for x_min in x_mins_list) and 
                          all(x_max == first_x_max for x_max in x_maxs_list))
        
        identical_all = identical_ranges and identical_modes and identical_steps and identical_limits
        
        return (identical_all,
                identical_ranges, list(map(list, first_ranges)) if identical_ranges else [],
                identical_modes, first_mode,
                identical_steps, first_step,
                identical_limits, first_x_min, first_x_max)
    
    def get_default_range(self, spectra):
        """Get default x_min and x_max from spectra.

        Returns the common intersection of all spectra's x-ranges
        (max of their individual minimums, min of their individual
        maximums) when that intersection is non-empty.

        If the selected spectra don't actually overlap (e.g. one spans
        499-998 and another 1493-1999), that intersection is empty and a
        literal max(x_mins)/min(x_maxs) calculation produces an inverted
        pair (x_min > x_max) — which is meaningless to show in the X-min/
        X-max fields and was previously displayed as-is. In that case we
        fall back to the full union of all spectra's ranges instead, so
        Reset always produces a sane, usable [x_min, x_max] pair.
        """
        if not spectra:
            return None, None
            
        x_mins = []
        x_maxs = []
        for spectrum in spectra:
            # Use original x_scale if it exists, otherwise use current x_scale
            x_scale = spectrum.get('original_x_scale', spectrum['x_scale'])
            if len(x_scale) > 0:
                x_mins.append(np.min(x_scale))
                x_maxs.append(np.max(x_scale))
        
        if not x_mins or not x_maxs:
            return None, None

        intersection_min, intersection_max = max(x_mins), min(x_maxs)
        if intersection_min <= intersection_max:
            return intersection_min, intersection_max

        # No real overlap between the selected spectra — fall back to the
        # full span covering all of them instead of an inverted pair.
        logger.warning(
            "get_default_range: selected spectra do not overlap "
            "(intersection [%s, %s] is empty); falling back to the full "
            "union range [%s, %s].",
            intersection_min, intersection_max, min(x_mins), max(x_maxs)
        )
        return min(x_mins), max(x_maxs)

    def linearize_spectrum(self, x_scale, y_scale, x_step):
        """
        Interpolate spectrum to have equidistant x values with given step.
        Supports both positive and negative steps.
        Uses x_min as the start point.
        """
        # Check for empty arrays
        if len(x_scale) == 0 or len(y_scale) == 0:
            return np.array([]), np.array([])
        
        # Sort x_scale and y_scale to ensure strictly increasing sequence
        sort_idx = np.argsort(x_scale)
        x_scale = x_scale[sort_idx]
        y_scale = y_scale[sort_idx]
        
        # Remove any duplicate x values by averaging corresponding y values
        unique_x, unique_idx = np.unique(x_scale, return_index=True)
        if len(unique_x) < len(x_scale):
            y_scale = binned_statistic(x_scale, y_scale, 'mean', bins=len(unique_x))[0]
            x_scale = unique_x
        
        # Handle different start/end points based on step sign
        if x_step > 0:
            # Positive step: increasing values
            first_point = self.x_min if self.x_min is not None else x_scale[0]
            max_possible = self.x_max if self.x_max is not None else x_scale[-1]
            
            # Ensure max_possible is greater than first_point
            if max_possible <= first_point:
                max_possible = x_scale[-1]
                if max_possible <= first_point:
                    # No valid range, return empty arrays
                    return np.array([]), np.array([])
        else:
            # Negative step: decreasing values
            first_point = self.x_max if self.x_max is not None else x_scale[-1]
            max_possible = self.x_min if self.x_min is not None else x_scale[0]
            
            # Ensure max_possible is less than first_point
            if max_possible >= first_point:
                max_possible = x_scale[0]
                if max_possible >= first_point:
                    # No valid range, return empty arrays
                    return np.array([]), np.array([])
        
        # Calculate number of complete steps that fit within the range
        # Use abs(x_step) to ensure positive number of intervals
        num_intervals = int(abs((max_possible - first_point) / x_step))
        last_point = first_point + num_intervals * x_step
        num_points = num_intervals + 1
        
        # Create points ensuring exact spacing
        x_new = np.linspace(first_point, last_point, num_points)
        
        # Create cubic spline interpolation
        cs = CubicSpline(x_scale, y_scale)
        
        # Interpolate y values at new x points
        y_new = cs(x_new)
        
        return x_new, y_new

    def get_spectrum_settings(self, spectrum):
        """Get all settings for a specific spectrum."""
        key = self._key_for(spectrum)
        return (self.spectrum_ranges.get(key, []),
                self.spectrum_exclude_modes.get(key, False),
                self.spectrum_x_steps.get(key, 1.0),
                self.spectrum_x_mins.get(key),
                self.spectrum_x_maxs.get(key))
             
    def apply_ranges_to_spectra(self, spectra):
        """Apply this manager's range/linearization/limit settings to
        *spectra*, per spectrum, honoring each spectrum's own per-spectrum
        overrides (spectrum_ranges / spectrum_exclude_modes /
        spectrum_x_steps) where set, falling back to the shared "current"
        values shown in the dialog.

        Returns a list of NEW, independent spectrum dicts — input spectra
        are never mutated in place.

        This used to be duplicated: SpectralRangeController had its own
        complete second copy of this same range/linearization/exclude
        logic, reachable from the actual commit path, while this method
        sat unused. Worse, they behaved differently — this one mutated its
        input spectra in place (stamping original_x_scale/original_y_scale
        directly onto whatever dicts were passed in), which is a landmine
        for the app's live spectrum data if this method were ever called
        on anything other than a disposable copy. Consolidated to one
        implementation, this one, always working on fresh copies; the
        controller now just calls this instead of reimplementing it.

        Previously there was also a fast-path special case — "if no
        range/linearization/limits are set globally, skip processing
        entirely" — that only checked the shared/global settings, not the
        per-spectrum dicts these same settings are stored in. Since a
        commit can (and does, via apply_settings_to_spectra) set different
        per-spectrum values, that shortcut could have silently skipped
        real per-spectrum settings for any future caller that didn't
        happen to keep the two in sync. The per-spectrum loop below reads
        spectrum_ranges/spectrum_x_steps/etc. directly and unconditionally
        for every spectrum, so there's no separate global-only shortcut
        left to go stale.
        """
        if not spectra:
            return []

        processed = []
        for spectrum in spectra:
            copy = {}
            for key, value in spectrum.items():
                if key in ('x_scale', 'y_scale'):
                    copy[key] = value.copy() if hasattr(value, 'copy') else value
                elif key == 'metadata':
                    copy[key] = value.copy() if hasattr(value, 'copy') else value
                else:
                    copy[key] = value
            processed.append(copy)

        for spectrum in processed:
            x_scale = spectrum['x_scale'].copy()
            y_scale = spectrum['y_scale'].copy()

            if len(x_scale) == 0:
                continue

            # 1. Overall X-axis limits (shared across all spectra in this commit)
            if self.x_min is not None and self.x_max is not None:
                mask = (x_scale >= self.x_min) & (x_scale <= self.x_max)
                x_scale = x_scale[mask]
                y_scale = y_scale[mask]

                if len(x_scale) == 0:
                    logger.warning(
                        "Spectrum '%s': X-axis limits [%s, %s] leave no data "
                        "points; spectrum will be empty.",
                        spectrum.get('label', '?'), self.x_min, self.x_max
                    )
                    spectrum['x_scale'] = x_scale
                    spectrum['y_scale'] = y_scale
                    continue

            # 2. Linearization, per-spectrum step falling back to the shared one
            if self.apply_linearization and len(x_scale) > 0:
                step = self.spectrum_x_steps.get(self._key_for(spectrum), self.x_step)
                x_scale, y_scale = self.linearize_spectrum(x_scale, y_scale, step)

            # 3. Include/exclude ranges, per-spectrum falling back to the shared ones
            ranges = self.spectrum_ranges.get(self._key_for(spectrum), [])
            is_exclude = self.spectrum_exclude_modes.get(self._key_for(spectrum), False)

            if ranges and len(x_scale) > 0:
                mask = np.zeros_like(x_scale, dtype=bool)
                for start, end in ranges:
                    start_idx = self.find_nearest_idx(x_scale, start)
                    end_idx = self.find_nearest_idx(x_scale, end)
                    mask[min(start_idx, end_idx):max(start_idx, end_idx) + 1] = True

                if is_exclude:
                    mask = ~mask

                x_scale = x_scale[mask]
                y_scale = y_scale[mask]

                if len(x_scale) == 0:
                    logger.warning(
                        "Spectrum '%s': the defined ranges (%s mode) leave no "
                        "data points; spectrum will be empty.",
                        spectrum.get('label', '?'),
                        'exclude' if is_exclude else 'include'
                    )

            spectrum['x_scale'] = x_scale
            spectrum['y_scale'] = y_scale

            # Shared, chronologically-ordered history across every
            # operation type that records one (see correction_history.py).
            # step is recorded as None when linearization wasn't applied,
            # rather than reporting self.x_step as if it had been used.
            step_used = None
            if self.apply_linearization:
                step_used = self.spectrum_x_steps.get(self._key_for(spectrum), self.x_step)
            spectrum['metadata'] = dict(spectrum.get('metadata') or {})
            spectrum['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'Data range',
                {
                    'ranges': ranges,
                    'exclude_mode': is_exclude,
                    'linearization_step': step_used,
                    'x_min': self.x_min,
                    'x_max': self.x_max,
                }
            )

        return processed
        
    def update_settings(self, settings):
        """Update the current settings."""
        if 'ranges' in settings:
            self.current_ranges = settings['ranges']
        if 'is_exclude_mode' in settings:
            self.is_exclude_mode = settings['is_exclude_mode']
        if 'x_step' in settings:
            self.x_step = settings['x_step']
        if 'x_min' in settings:
            self.x_min = settings['x_min']
        if 'x_max' in settings:
            self.x_max = settings['x_max']
        if 'apply_linearization' in settings:
            self.apply_linearization = settings['apply_linearization']