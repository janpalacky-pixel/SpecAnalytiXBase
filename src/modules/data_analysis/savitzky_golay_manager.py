
# src/modules/data_analysis/savitzky_golay_manager.py

import numpy as np
from scipy.signal import savgol_filter
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress
logger = get_logger(__name__)

class SavitzkyGolayManager:
    """Business logic for Savitzky-Golay filtering operations on spectra."""
    
    def __init__(self):
        self.window_length = 11  # Default window length (must be odd)
        self.polyorder = 3  # Default polynomial order
        self.deriv_order = 0  # Default derivative order (0 = smoothing only)
        self.delta = 1.0  # Default delta for derivatives
        self.mode = 'interp'  # Default edge handling mode

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum key — uses the spectrum's persistent
        unique_id rather than its label. Labels are not stable
        identifiers: renaming a spectrum doesn't change its identity, and
        two unrelated spectra (e.g. from separate import sessions, or a
        re-imported file producing the same filename-derived label) can end
        up sharing a label even though they've never had anything to do
        with each other. Used by SavitzkyGolayDialog for
        main_controller.sg_delta_values — the persistent per-spectrum
        custom-delta override store — so a rename doesn't orphan a
        spectrum's custom delta and a re-imported spectrum that reuses an
        old label doesn't silently inherit one."""
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum['label']
    
    def _ensure_valid_parameters(self, window_length, polyorder, deriv_order):
        """
        Ensure parameters meet Savitzky-Golay requirements.
        
        Args:
            window_length: Window length parameter
            polyorder: Polynomial order parameter
            deriv_order: Derivative order parameter
            
        Returns:
            Tuple of valid (window_length, polyorder, deriv_order)
        """
        # Ensure window length is odd
        if window_length % 2 == 0:
            window_length += 1
        
        # Polynomial order must be less than window length
        polyorder = min(polyorder, window_length - 1)
        
        # Derivative order must be <= polynomial order
        deriv_order = min(deriv_order, polyorder)
        
        return window_length, polyorder, deriv_order

    def apply_sg_filter(self, spectra, settings=None, progress_callback=None):
        """
        Apply Savitzky-Golay filtering to spectra.
        
        Args:
            spectra: List of spectrum dictionaries
            settings: Dictionary of Savitzky-Golay settings
            progress_callback: optional callable, invoked every 50 spectra
                during the per-spectrum loop below — see
                SNIPBaselineManager.apply_correction for the full
                reasoning; same hook/contract. None (the default) — no
                change from before.
            
        Returns:
            List of filtered spectra
        """
        # Update manager settings if provided
        if settings:
            self.update_settings(settings)
        
        # Check for delta values - support both old and new naming conventions
        delta_values = {}
        if settings:
            # Check both possible keys for backward compatibility
            if 'delta_values' in settings:
                delta_values = settings['delta_values']
            elif 'individual_delta_values' in settings:
                delta_values = settings['individual_delta_values']
        
        # Calculate estimated delta values for all spectra
        estimated_delta_values = {}
        for spectrum in spectra:
            x_scale = spectrum['x_scale']
            if len(x_scale) >= 2:
                diffs = np.diff(x_scale)
                median_diff = np.median(np.abs(diffs))
                # Use a more relaxed check for "close enough to equidistant"
                # Accept data where standard deviation is less than 50% of median (was 10% before)
                # This handles "nearly equidistant" data better
                if np.std(diffs) < 0.5 * median_diff:  # More relaxed condition
                    estimated_delta_values[spectrum['label']] = median_diff
        
        # Create a storage for processed spectra
        processed_spectra = []
        
        # Apply SG filter to each spectrum
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            # Make a copy of the spectrum
            processed_spectrum = spectrum.copy()
            
            # Get current y data
            y_scale = spectrum['y_scale'].copy()
            x_scale = spectrum['x_scale'].copy()
            
            # Skip empty spectra
            if len(y_scale) == 0:
                processed_spectra.append(processed_spectrum)
                continue
            
            # Ensure we have enough points for the window
            min_points = max(3, self.window_length)
            if len(y_scale) < min_points:
                logger.warning(f"Warning: Spectrum '{spectrum['label']}' has only {len(y_scale)} points, " f"which is too few for a window of {self.window_length}. " f"Using smaller window.")
                # Adjust window length while keeping it odd
                window_length = len(y_scale) - (2 if len(y_scale) % 2 == 0 else 1)
                if window_length < 3:
                    window_length = 3  # Minimum valid window length
            else:
                window_length = self.window_length
            
            # Ensure parameters are valid for SG filter
            window_length, polyorder, deriv_order = self._ensure_valid_parameters(
                window_length, self.polyorder, self.deriv_order)
            
            # Determine delta for this spectrum
            delta = 1.0  # Default fallback if nothing else is available
            
            # Priority for delta value:
            # 1. Custom delta value specified by user
            # 2. Estimated delta value from spectrum data
            # 3. Default delta value (1.0)
            if spectrum['label'] in delta_values:
                delta = delta_values[spectrum['label']]
                delta_source = "custom"
            elif spectrum['label'] in estimated_delta_values:
                delta = estimated_delta_values[spectrum['label']]
                delta_source = "estimated"
            else:
                delta_source = "default"
            
            # Print debug info to see what's happening
            logger.debug(f"Spectrum: {spectrum['label']}, " f"Delta: {delta}, Source: {delta_source}")
            
            try:
                # Apply Savitzky-Golay filter
                filtered_y = savgol_filter(
                    y_scale,
                    window_length=window_length,
                    polyorder=polyorder,
                    deriv=deriv_order,
                    delta=delta,
                    mode=self.mode
                )
                
                # Update spectrum with filtered data
                processed_spectrum['y_scale'] = filtered_y
                
                # Store SG filter info in the spectrum
                processed_spectrum['sg_filter_info'] = {
                    'window_length': window_length,
                    'polyorder': polyorder,
                    'deriv_order': deriv_order,
                    'delta': delta,  # Store the actual delta used
                    'delta_source': delta_source,  # Store the source of the delta value
                    'mode': self.mode
                }

                # processed_spectrum = spectrum.copy() above is a SHALLOW
                # copy — processed_spectrum['metadata'] is still the exact
                # same dict object as spectrum['metadata'] unless replaced
                # with its own copy first. Writing into it below would
                # silently mutate the ORIGINAL spectrum's metadata too, as
                # a side effect of building what's supposed to be an
                # independent filtered copy (see the shallow-copy metadata
                # bug pattern in 00_SHARED_PROCESS.md).
                processed_spectrum['metadata'] = dict(processed_spectrum.get('metadata') or {})

                # Shared, chronologically-ordered history across every
                # operation type that records one (see
                # correction_history.py) — so a spectrum smoothed, then
                # baseline-corrected, then smoothed again shows all three
                # in the order they actually happened, tagged by which
                # operation each one was.
                processed_spectrum['metadata']['correction_history'] = append_correction_history(
                    spectrum.get('metadata'), 'SG-smoothing', processed_spectrum['sg_filter_info']
                )
                
            except Exception as e:
                logger.error(f"Error applying Savitzky-Golay filter to " f"spectrum '{spectrum['label']}': {str(e)}")
                # Keep original data
                processed_spectrum['y_scale'] = y_scale
            
            # Add to result list
            processed_spectra.append(processed_spectrum)
        
        return processed_spectra
    
    def update_settings(self, settings):
        """Update Savitzky-Golay filter settings."""
        if 'window_length' in settings:
            self.window_length = settings['window_length']
        if 'polyorder' in settings:
            self.polyorder = settings['polyorder']
        if 'deriv_order' in settings:
            self.deriv_order = settings['deriv_order']
        if 'delta' in settings:
            self.delta = settings['delta']
        if 'mode' in settings:
            self.mode = settings['mode']
    
    def estimate_delta_from_spectrum(self, spectrum):
        """
        Estimate the optimal delta value from a spectrum's x-scale.
        
        Args:
            spectrum: Spectrum dictionary with x_scale
            
        Returns:
            Estimated delta value, or None if estimation fails
        """
        x_scale = spectrum.get('x_scale', [])
        if len(x_scale) < 2:
            return None
            
        # Calculate differences between consecutive points
        diffs = np.diff(x_scale)
        # Use median difference (more robust than mean)
        median_diff = np.median(np.abs(diffs))
        # Check if reasonably equidistant — same relaxed 0.5 threshold as
        # apply_sg_filter's own equidistance check (see that method's
        # comment: "This handles 'nearly equidistant' data better"). This
        # used to be a stricter 0.1 here — three different
        # equidistant-enough thresholds (0.5, 0.1, 0.1) scattered across
        # this file meant the SAME spectrum could be judged equidistant by
        # one check and not by another, depending on which happened to be
        # called.
        std_diff = np.std(diffs)
        if std_diff > 0.5 * median_diff:
            # Non-equidistant data
            return None
            
        return median_diff
    
    def check_equidistance(self, spectrum):
        """
        Check if a spectrum's x-scale is reasonably equidistant.
        
        Args:
            spectrum: Spectrum dictionary with x_scale
            
        Returns:
            Tuple of (is_equidistant, delta, variance)
        """
        x_scale = spectrum.get('x_scale', [])
        if len(x_scale) < 2:
            return False, None, None
            
        # Calculate differences between consecutive points
        diffs = np.diff(x_scale)
        # Get statistics
        median_diff = np.median(np.abs(diffs))
        variance = np.var(diffs)
        std_diff = np.std(diffs)
        
        # Consider equidistant using the same relaxed 0.5 threshold as
        # apply_sg_filter's own check — see estimate_delta_from_spectrum's
        # comment above for why these were consolidated to agree.
        is_equidistant = std_diff < 0.5 * median_diff
        
        return is_equidistant, median_diff, variance