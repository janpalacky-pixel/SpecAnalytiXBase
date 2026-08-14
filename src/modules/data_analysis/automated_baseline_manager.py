# src/modules/data_analysis/automated_baseline_manager.py

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from src.modules.utils.app_logger import get_logger
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)

class AutomatedBaselineManager:
    """
    Business logic for automated baseline correction using the
    Asymmetric Least Squares (ALS) algorithm with region exclusion.
    """

    def __init__(self):
        # Labels of any spectra whose correction failed on the most
        # recent apply_correction() call — see that method's docstring.
        self.failed_labels = []

    def calculate_als_baseline(self, y, lam, p, niter=10, exclude_indices=None):
        """
        Calculates a baseline using ALS, ignoring specified regions.
        This version is more robust against numerical errors.
        """
        L = len(y)
        D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(L - 2, L))
        D = lam * D.transpose().dot(D)
        
        w = np.ones(L)
        
        try:
            for i in range(niter):
                W = sparse.spdiags(w, 0, L, L)
                Z = W + D
                z = spsolve(Z, w * y)
                
                w_new = p * (y > z) + (1 - p) * (y <= z)
                
                # Enforce exclusion regions in every iteration
                if exclude_indices is not None:
                    w = w_new * ~exclude_indices
                else:
                    w = w_new
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during ALS fitting: {e}")
            return np.full_like(y, np.nan) # Return NaN array on failure

        # If regions were excluded, we must interpolate the baseline through them
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            
            # We need at least 2 points to interpolate across the whole spectrum
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan) # Cannot interpolate
                
            # Perform linear interpolation to fill the gaps in the baseline
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def apply_correction(self, spectra: list, params: dict, progress_callback=None) -> list:
        """
        Applies the ALS baseline correction to a list of spectra.

        Each returned spectrum's metadata['correction_history'] gets a new
        'Automated Baseline' entry that includes a 'success' flag.
        Previously this metadata was written unconditionally, claiming a
        specific ALS correction (with its exact lambda/p/iteration values)
        had been applied even when the baseline computation failed and
        y_scale was left completely unchanged — e.g. because the selected
        fitting regions excluded every point, leaving nothing to fit or
        interpolate through. That made the metadata actively misleading:
        it recorded a correction that never actually happened, with no
        way to tell afterward (from the spectrum's own record) that it
        hadn't. failed_labels is also attached to the manager
        (self.failed_labels) after each call so the caller can surface a
        warning — the manager only logs failures, which is invisible in
        the running app.

        progress_callback : optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before.
        """
        lam = params.get('lambda', 1e6)
        p = params.get('p', 0.01)
        n_iter = params.get('n_iter', 10)
        fitting_ranges = params.get('fitting_ranges', [])
        invert_regions = params.get('invert_regions', False)

        corrected_spectra = []
        self.failed_labels = []
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            corrected_spectrum = {key: (value.copy() if hasattr(value, 'copy') else value)
                                  for key, value in spectrum.items()}

            y_scale = corrected_spectrum['y_scale']
            x_scale = corrected_spectrum['x_scale']

            # Create the region mask from user-defined ranges
            region_mask = np.zeros_like(x_scale, dtype=bool)
            if fitting_ranges:
                for start, end in fitting_ranges:
                    low, high = min(start, end), max(start, end)
                    region_mask |= (x_scale >= low) & (x_scale <= high)
            
            # If "Invert" is checked, we exclude everything OUTSIDE the selected regions.
            exclude_mask = ~region_mask if invert_regions else region_mask
            
            # Calculate the baseline
            baseline = self.calculate_als_baseline(y_scale, lam=lam, p=p, niter=n_iter, exclude_indices=exclude_mask)
            
            # Subtract the baseline (only if calculation was successful)
            success = baseline is not None and not np.isnan(baseline).all()
            if success:
                corrected_spectrum['y_scale'] = y_scale - baseline
            else:
                self.failed_labels.append(spectrum.get('label', '?'))
                logger.warning(
                    "Automated baseline correction failed for '%s' — "
                    "spectrum left unchanged (see the warning/error above "
                    "for the specific reason).",
                    spectrum.get('label', '?')
                )
            
            # Store correction info in metadata
            if 'metadata' not in corrected_spectrum:
                corrected_spectrum['metadata'] = {}
            
            entry_fields = {
                'success': success,
                'algorithm': 'ALS', 'lambda': lam, 'p': p,
                'iterations': n_iter, 'fitting_ranges': fitting_ranges,
                'inverted_regions': invert_regions
            }
            # Shared, chronologically-ordered history across every
            # operation type that records one (see correction_history.py).
            # This used to ALSO be written as a separate flat
            # metadata['auto_baseline_correction'] key holding the exact
            # same dict — nothing else in the codebase ever read that key
            # (confirmed by search), so it was pure dead weight that just
            # made this one correction show up twice in the metadata
            # viewer dialog (once as its own section, once again inside
            # Correction History). Removed; correction_history alone is
            # the single source of truth now, same as every other
            # operation in this file's family.
            corrected_spectrum['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'Automated Baseline', entry_fields
            )
            corrected_spectra.append(corrected_spectrum)
            
        return corrected_spectra