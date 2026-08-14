# src/modules/data_analysis/baseline_manager.py

import numpy as np
from numpy.polynomial.polynomial import polyfit, polyval
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)

class BaselineManager:
    """
    Manager class for handling baseline correction operations.
    Stores baseline points for each spectrum and provides methods for fitting and correction.
    """
    
    def __init__(self):
        """Initialize the baseline manager."""
        self.baseline_points = {}  # Dictionary mapping spectrum keys to baseline points
        self.fit_types = {}  # Dictionary mapping spectrum keys to fit type
        self.poly_orders = {}  # Dictionary mapping spectrum keys to polynomial order
        self.correction_info = {}  # Additional metadata for each spectrum's correction
        
        # Default settings
        self.default_fit_type = "cubic spline"
        self.default_poly_order = 5

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum key for the dicts below — uses the spectrum's
        persistent unique_id rather than its label. Labels are not stable
        identifiers: renaming a spectrum doesn't change its identity, and
        two unrelated spectra (e.g. from separate import sessions, or a
        re-imported file producing the same filename-derived label) can end
        up sharing a label even though they've never had anything to do
        with each other. Falls back to label only if a spectrum genuinely
        has no unique_id, which shouldn't normally happen.

        Every read/write of baseline_points / fit_types / poly_orders /
        correction_info must go through this helper (or be given a key
        already derived from it) — never index those dicts with a raw
        spectrum['label'] directly."""
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum['label']

    def prune_to_current_spectra(self, current_spectra):
        """Remove per-spectrum entries (points/fit type/order/info) for any
        key not belonging to a spectrum in current_spectra. Without this, a
        spectrum that's gone (cleared, replaced by a new import) leaves its
        old baseline points/settings behind forever, keyed by whatever
        identified it at the time — and if a later import happens to reuse
        that same label, it would silently inherit them."""
        current_keys = {self._key_for(s) for s in current_spectra}
        for d in (self.baseline_points, self.fit_types, self.poly_orders, self.correction_info):
            for key in list(d.keys()):
                if key not in current_keys:
                    del d[key]

    def add_baseline_point(self, key, x, y):
        """
        Add a baseline point for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for(). Callers should
                pass _key_for(spectrum), not a raw spectrum['label'].
            x (float): X-coordinate of the point
            y (float): Y-coordinate of the point
        
        Returns:
            list: Updated list of baseline points
        """
        if key not in self.baseline_points:
            self.baseline_points[key] = []
            self.fit_types[key] = self.default_fit_type
            self.poly_orders[key] = self.default_poly_order
            self.correction_info[key] = {}
        
        # Add point and sort by x-coordinate
        self.baseline_points[key].append((x, y))
        self.baseline_points[key].sort(key=lambda point: point[0])
        
        return self.baseline_points[key]
    
    def remove_baseline_point(self, key, x, y, tolerance=0.01):
        """
        Remove a baseline point close to the given coordinates.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            x (float): X-coordinate of the point
            y (float): Y-coordinate of the point
            tolerance (float): Maximum distance for point removal
            
        Returns:
            list: Updated list of baseline points or None if no points exist
        """
        if key not in self.baseline_points:
            return None
        
        points = self.baseline_points[key]
        for i, (px, py) in enumerate(points):
            # Calculate distance
            dist = np.sqrt((px - x)**2 + (py - y)**2)
            if dist <= tolerance:
                points.pop(i)
                break
        
        return points
    
    def set_fit_type(self, key, fit_type):
        """
        Set the fit type for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            fit_type (str): Type of fit ('cubic spline', 'polynomial', etc.)
        """
        if key not in self.fit_types:
            self.fit_types[key] = self.default_fit_type
            self.poly_orders[key] = self.default_poly_order
            self.baseline_points[key] = []
            self.correction_info[key] = {}
        
        self.fit_types[key] = fit_type
    
    def set_poly_order(self, key, order):
        """
        Set the polynomial order for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            order (int): Polynomial order
        """
        if key not in self.poly_orders:
            self.poly_orders[key] = self.default_poly_order
            self.fit_types[key] = self.default_fit_type
            self.baseline_points[key] = []
            self.correction_info[key] = {}
        
        self.poly_orders[key] = order
    
    def clear_baseline(self, key):
        """
        Clear all baseline points for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
        """
        if key in self.baseline_points:
            self.baseline_points[key] = []
            self.correction_info[key] = {}
    
    def clear_all_baselines(self):
        """Clear all baseline points for all spectra."""
        self.baseline_points = {}
        self.correction_info = {}
        # Keep fit types and poly orders
    
    def get_baseline_points(self, key):
        """
        Get the baseline points for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            
        Returns:
            list: List of baseline points or empty list if none exist
        """
        return self.baseline_points.get(key, [])
    
    def get_fit_type(self, key):
        """
        Get the fit type for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            
        Returns:
            str: Fit type or default fit type if not set
        """
        return self.fit_types.get(key, self.default_fit_type)
    
    def get_poly_order(self, key):
        """
        Get the polynomial order for a spectrum.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            
        Returns:
            int: Polynomial order or default order if not set
        """
        return self.poly_orders.get(key, self.default_poly_order)
    
    def calculate_baseline(self, key, x_values):
        """
        Calculate baseline values for a given spectrum and x-values.
        
        Args:
            key (str): Per-spectrum key — see _key_for().
            x_values (numpy.ndarray): X-values to calculate baseline for
            
        Returns:
            numpy.ndarray: Baseline y-values or None if not enough points
        """
        # Error handling if input is invalid
        if x_values is None or len(x_values) == 0:
            logger.debug(f"Empty x_values provided for {key}")
            return None
            
        if key not in self.baseline_points:
            logger.debug(f"No baseline points stored for {key}")
            return None
        
        points = self.baseline_points[key]
        if len(points) < 2:  # Need at least 2 points for interpolation
            logger.warning(f"Not enough baseline points for {key} (need at least 2)")
            return None
        
        try:
            x_points, y_points = zip(*points)
            x_points = np.array(x_points)
            y_points = np.array(y_points)
            
            fit_type = self.get_fit_type(key)
            
            # Save info for summary
            self.correction_info[key] = {
                'points': len(points),
                'type': fit_type
            }
            
            # Check if x_points has the same values (horizontal line)
            if np.allclose(x_points, x_points[0]):
                logger.warning(f"Warning: All x-coordinates are identical for {key}, using flat line")
                return np.full_like(x_values, np.mean(y_points))
                
            # Check if x_values is within the range of x_points
            x_min, x_max = np.min(x_points), np.max(x_points)
            if np.min(x_values) < x_min or np.max(x_values) > x_max:
                logger.debug("Baseline extrapolation: x_values range [%s, %s] exceeds points range [%s, %s] for %s",
                             np.min(x_values), np.max(x_values), x_min, x_max, key)
                # Continue anyway - extrapolation will be performed
            
            if fit_type == 'cubic spline':
                # Ensure x_points is sorted and has unique values
                if len(x_points) != len(np.unique(x_points)):
                    logger.warning(f"Warning: Duplicate x values in baseline points for {key}")
                    # Handle case with duplicate x values
                    # Keep only unique x values with their corresponding y values
                    unique_indices = np.unique(x_points, return_index=True)[1]
                    x_points = x_points[unique_indices]
                    y_points = y_points[unique_indices]
                
                if len(x_points) < 2:
                    logger.warning(f"Not enough unique baseline points for {key} after removing duplicates")
                    return None
                    
                try:
                    from scipy.interpolate import CubicSpline
                    cs = CubicSpline(x_points, y_points)
                    return cs(x_values)
                except Exception as e:
                    logger.error(f"Error in cubic spline for {key}: {e}")
                    # Fall back to polynomial if cubic spline fails
                    logger.warning(f"Falling back to polynomial interpolation for {key}")
                    baseline, effective_order = self._calculate_polynomial_baseline(
                        x_points, y_points, x_values, 3)
                    # correction_info still said fit_type == 'cubic spline'
                    # at this point (set from get_fit_type(key) above) —
                    # update it to reflect what was actually fit, not what
                    # was requested and silently could not be used.
                    self.correction_info[key]['type'] = 'polynomial (spline fallback)'
                    self.correction_info[key]['order'] = effective_order
                    return baseline
            
            elif fit_type == 'polynomial':
                order = self.get_poly_order(key)
                baseline, effective_order = self._calculate_polynomial_baseline(
                    x_points, y_points, x_values, order)
                # Record what was ACTUALLY used, not what was requested —
                # these can differ (see _calculate_polynomial_baseline's
                # docstring): too few baseline points silently caps the
                # order, and recording the requested order regardless
                # made the stored/displayed/exported correction record
                # inaccurate about what the correction actually did.
                self.correction_info[key]['order'] = effective_order
                return baseline
            
            # Fallback to PCHIP interpolation which can handle non-monotonic data better
            try:
                from scipy.interpolate import PchipInterpolator
                pchip = PchipInterpolator(x_points, y_points)
                return pchip(x_values)
            except Exception as e:
                logger.error(f"Error in PCHIP interpolation for {key}: {e}")
                logger.warning(f"Falling back to simple linear interpolation for {key}")
                # Last resort: linear interpolation
                from scipy.interpolate import interp1d
                try:
                    # Sort points first to ensure monotonicity
                    sort_idx = np.argsort(x_points)
                    x_sorted = x_points[sort_idx]
                    y_sorted = y_points[sort_idx]
                    f = interp1d(x_sorted, y_sorted, bounds_error=False, fill_value="extrapolate")
                    return f(x_values)
                except Exception as e2:
                    logger.error(f"Even linear interpolation failed for {key}: {e2}")
                    return None
        except Exception as e:
            logger.error(f"Unexpected error in calculate_baseline for {key}: {e}")
            import traceback
            logger.debug("<traceback>")
            return None
    
    def _calculate_polynomial_baseline(self, x_points, y_points, x_values, order):
        """
        Calculate polynomial baseline.
        
        Args:
            x_points (numpy.ndarray): X-coordinates of baseline points
            y_points (numpy.ndarray): Y-coordinates of baseline points
            x_values (numpy.ndarray): X-values to calculate baseline for
            order (int): Requested polynomial order
            
        Returns:
            (numpy.ndarray, int): baseline y-values, and the EFFECTIVE
            order actually used to compute them. These can differ from
            the requested order — a polynomial of order N needs at least
            N+1 points, so with too few baseline points the order is
            silently capped. Callers must record the returned effective
            order, not the one they asked for — previously the caller
            recorded the requested order regardless of what was actually
            fit, so e.g. asking for order 8 with only 3 points available
            (capped to order 2) would be saved/displayed/exported as
            "order 8", an inaccurate record of what the correction
            actually did.
        """
        # Limit order based on number of points
        effective_order = min(order, len(x_points) - 1)
        if effective_order < 1:
            effective_order = 1

        if effective_order != order:
            logger.warning(
                "Requested polynomial order %d needs at least %d baseline "
                "points; only %d are defined, so order %d is used instead.",
                order, order + 1, len(x_points), effective_order
            )

        try:
            coeffs = polyfit(x_points, y_points, effective_order)
            return polyval(x_values, coeffs), effective_order
        except Exception as e:
            logger.error(f"Error in polynomial fit: {e}")
            return None, effective_order
    
    def apply_baseline_correction(self, spectrum):
        """
        Apply baseline correction to a spectrum.
        
        Args:
            spectrum (dict): Spectrum dictionary with 'x_scale', 'y_scale', and 'label'
            
        Returns:
            dict: Corrected spectrum or original if correction not possible
        """
        key = self._key_for(spectrum)
        x_scale = spectrum['x_scale']
        y_scale = spectrum['y_scale']
        
        # Calculate baseline
        baseline = self.calculate_baseline(key, x_scale)
        if baseline is None:
            return spectrum
        
        # Create a copy of the spectrum
        corrected_spectrum = spectrum.copy()
        
        # Make deep copies of arrays
        corrected_spectrum['x_scale'] = x_scale.copy()
        corrected_spectrum['y_scale'] = y_scale.copy() - baseline
        
        # Store the baseline for possible undo/display
        if 'original_y_scale' not in corrected_spectrum:
            corrected_spectrum['original_y_scale'] = y_scale.copy()
        corrected_spectrum['baseline_y_scale'] = baseline
        
        # spectrum.copy() above is a SHALLOW copy — corrected_spectrum['metadata']
        # was still the exact same dict object as spectrum['metadata'] whenever
        # the input spectrum already had one (i.e. on every application after the
        # first). Writing into it below would have silently mutated the ORIGINAL
        # spectrum's metadata too, as a side effect of building what's supposed
        # to be an independent corrected copy. Giving corrected_spectrum its own
        # copy of the metadata dict here avoids that.
        corrected_spectrum['metadata'] = dict(corrected_spectrum.get('metadata') or {})

        # Shared, chronologically-ordered history across every operation
        # type that records one (see correction_history.py) — so a
        # spectrum corrected by SVD Background, then this, then SVD
        # Background again shows all three in the order they actually
        # happened, tagged by which operation each one was, rather than
        # this operation keeping its own separate, disconnected record
        # (previously metadata['baseline_correction'], a single dict
        # overwritten on every reapplication with no history at all).
        #
        # self.correction_info[key] only ever holds a point COUNT
        # ('points': len(points)), never the actual (x, y) coordinates —
        # those live separately in self.baseline_points[key], the live,
        # in-memory manager state. The dialog's only other way to recover
        # real coordinates afterward is operations_manager.get_baseline_
        # points(), which reads a 'baseline_state' snapshot attached to
        # the ORIGINAL "Manual baseline" operation record — a record that
        # gets popped and discarded in Add as New mode (replaced by
        # register_copy_operation()'s generic copy record, which never
        # carries baseline_state at all). Confirmed: this left "Add as
        # New" always showing "Point Count: 0" / "No baseline points
        # defined for this spectrum", even though the count and fit type
        # displayed correctly (those came from correction_info above).
        # Including the actual coordinates directly in the history entry
        # itself — while self.baseline_points[key] is still live, i.e.
        # right here, before commit_manual_baseline's later cleanup
        # clears it — means the detail dialog can use them directly
        # without needing that separate, mode-fragile lookup at all.
        entry_data = dict(self.correction_info.get(key, {}))
        entry_data['point_coordinates'] = [list(p) for p in self.baseline_points.get(key, [])]
        corrected_spectrum['metadata']['correction_history'] = append_correction_history(
            spectrum.get('metadata'), 'Manual baseline', entry_data
        )
        
        return corrected_spectrum
    
    def get_correction_summary(self, spectra=None):
        """
        Get a summary of all baseline corrections.

        Args:
            spectra: Optional list of currently-known spectra, used to
                resolve each internal key back to that spectrum's CURRENT
                label, so a rename is reflected immediately rather than
                showing whatever name was current when the points were
                placed. Falls back to the raw key if a key has no match
                (e.g. the spectrum was removed since).
        
        Returns:
            list: List of dictionaries with correction info
        """
        key_to_label = {}
        if spectra:
            key_to_label = {self._key_for(s): s.get('label', '') for s in spectra}

        summary = []
        
        for key, info in self.correction_info.items():
            if 'points' not in info or info['points'] == 0:
                continue
                
            entry = {
                'spectrum': key_to_label.get(key, key),
                'points': info.get('points', 0),
                'type': info.get('type', self.default_fit_type)
            }
            
            if 'order' in info:
                entry['order'] = info['order']
                
            summary.append(entry)
            
        return summary