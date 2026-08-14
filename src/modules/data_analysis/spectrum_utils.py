
# src/modules/data_analysis/spectrum_utils.py

import numpy as np

class SpectrumStatisticsCalculator:
    """Helper class to calculate statistics for spectral data"""
    
    def __init__(self, manager):
        """
        Initialize with spectral range manager.
        
        Args:
            manager: SpectralRangeManager instance
        """
        self.manager = manager  # Store manager reference directly
    
    def _calculate_step_stats(self, x_scale):
        """Calculate step statistics for x_scale."""
        if len(x_scale) > 1:
            steps = np.diff(x_scale)
            avg_step = np.mean(steps)
            step_var = np.var(steps)
            return avg_step, step_var
        else:
            return 0, 0
    
    def get_spectrum_ranges(self, spectrum):
        """Get ranges for a specific spectrum."""
        return self.manager.spectrum_ranges.get(spectrum['label'], [])
    
    def get_spectrum_statistics(self, spectrum, use_original=False):
        """Calculate statistics for a spectrum."""
        if use_original:
            x_scale = spectrum.get('original_x_scale', spectrum['x_scale'])
            # Calculate step statistics for original data
            avg_step, step_var = self._calculate_step_stats(x_scale)
            mode = "No ranges"
        else:
            # Get spectrum's current x_scale for Xmin, Xmax, and Points
            x_scale = spectrum['x_scale']
            
            # For step statistics, use the x_scale before range restrictions
            # Start with original data
            x_scale_for_steps = spectrum.get('original_x_scale', spectrum['x_scale']).copy()
            y_scale_for_steps = spectrum.get('original_y_scale', spectrum['y_scale']).copy()
            
            # Apply common range
            if self.manager.x_min is not None and self.manager.x_max is not None:
                mask = (x_scale_for_steps >= self.manager.x_min) & (x_scale_for_steps <= self.manager.x_max)
                x_scale_for_steps = x_scale_for_steps[mask]
                y_scale_for_steps = y_scale_for_steps[mask]

            # Apply linearization if needed
            if self.manager.apply_linearization and len(x_scale_for_steps) > 0:
                # Get spectrum-specific step
                label = spectrum['label']
                x_step = self.manager.spectrum_x_steps.get(label, self.manager.x_step)
                
                # Use manager's linearize_spectrum method
                x_scale_for_steps, _ = self.manager.linearize_spectrum(
                    x_scale_for_steps, y_scale_for_steps, x_step
                )

            # Calculate step statistics
            avg_step, step_var = self._calculate_step_stats(x_scale_for_steps)

            # Get spectrum-specific mode
            label = spectrum['label']
            ranges = self.manager.spectrum_ranges.get(label, [])
            is_exclude = self.manager.spectrum_exclude_modes.get(label, False)
            mode = "Exclude Ranges" if is_exclude else "Include Ranges" if ranges else "No ranges"
        
        # Calculate remaining statistics from current x_scale
        if len(x_scale) > 1:
            x_min = np.min(x_scale)
            x_max = np.max(x_scale)
            n_points = len(x_scale)
        else:
            x_min = x_max = 0 if len(x_scale) == 0 else x_scale[0]
            n_points = len(x_scale)
        
        return avg_step, step_var, x_min, x_max, n_points, mode