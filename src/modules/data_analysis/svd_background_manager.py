# src/modules/data_analysis/svd_background_manager.py

import numpy as np
from scipy import interpolate
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
from src.modules.utils.progress_utils import notify_progress
logger = get_logger(__name__)

class SVDBackgroundManager:
    """Business logic for SVD background correction operations on spectra."""
    
    def __init__(self):
        self.correction_mode = "all_subspectra"
        self.max_components = 10
        self.selected_subspectra = [0, 1, 2]
        self.baseline_corrections = {}
        self.baseline_points = {}
        self.baseline_settings = {}
        self.inverted_subspectra = set()  # Track inverted subspectra
        
        # SVD components (computed once per correction operation)
        self.U = None
        self.s = None
        self.Vt = None
        self.x_axis = None
        self.corrected_U = None
        self.explained_variance = None
        
    def set_selected_subspectra(self, selected_indices):
        """Set which subspectra are selected for reconstruction."""
        self.selected_subspectra = selected_indices.copy() if selected_indices else []
        logger.debug(f"DEBUG: Updated selected subspectra to: {self.selected_subspectra}")
    
    def set_correction_mode(self, mode):
        """Set the correction mode."""
        self.correction_mode = mode
        logger.debug(f"DEBUG: Updated correction mode to: {self.correction_mode}")
    
    def set_max_components(self, max_components):
        """Set maximum number of components for 'first_n' mode."""
        self.max_components = max_components
        logger.debug(f"DEBUG: Updated max components to: {self.max_components}")

    def invert_subspectrum(self, subspectrum_index):
        """
        Manually invert a subspectrum by multiplying U and Vt by -1.
        
        Args:
            subspectrum_index: Index of subspectrum to invert
            
        Returns:
            bool: True if inversion was successful
        """
        if self.U is None or subspectrum_index >= self.U.shape[1]:
            return False
            
        # Clear any existing baseline corrections to avoid coordinate system conflicts
        if subspectrum_index in self.baseline_corrections:
            self.clear_baseline(subspectrum_index)
            
        # Update inversion tracking
        if subspectrum_index in self.inverted_subspectra:
            self.inverted_subspectra.remove(subspectrum_index)
        else:
            self.inverted_subspectra.add(subspectrum_index)
        
        # Invert the subspectrum and coefficients
        self.U[:, subspectrum_index] *= -1
        self.Vt[subspectrum_index, :] *= -1
        
        if self.corrected_U is not None:
            self.corrected_U[:, subspectrum_index] = self.U[:, subspectrum_index]
        
        return True

    def compute_svd_from_spectra(self, spectra):
        """
        Compute SVD from input spectra using standard numpy SVD.
        
        Args:
            spectra: List of spectrum dictionaries with 'x_scale', 'y_scale', 'label'
            
        Returns:
            bool: True if SVD computation was successful
        """
        if not spectra:
            logger.debug("DEBUG: No spectra provided for SVD computation")
            return False
            
        try:
            logger.debug(f"DEBUG: Computing SVD from {len(spectra)} spectra")
            
            # Extract x and y data from spectra
            x_scales = [spectrum['x_scale'] for spectrum in spectra]
            y_scales = [spectrum['y_scale'] for spectrum in spectra]
            
            logger.debug(f"DEBUG: First spectrum x-axis length: {len(x_scales[0])}")
            logger.debug(f"DEBUG: First spectrum y-axis length: {len(y_scales[0])}")
            
            # Check if all spectra have the same x-axis.
            #
            # This must use the same tolerance-aware comparison
            # (spectra_validation.axes_match) as validate_common_x_axis,
            # which already ran before this dialog was even allowed to
            # open and already told the user their spectra match. An
            # exact np.array_equal() check here is STRICTER than that
            # up-front promise — two axes that are physically identical
            # (e.g. one rebuilt arithmetically via Data Range
            # linearisation, differing from the other only in the last
            # bit of float precision) would pass the up-front check, let
            # the dialog open, and then fail here with a confusing "SVD
            # computation failed" even though the user was just told
            # their spectra were compatible.
            first_x = x_scales[0]
            for i, x in enumerate(x_scales):
                if not axes_match(first_x, x):
                    logger.error(
                        "SVD background: %s",
                        describe_axis_mismatch(spectra[0], spectra[i], 'SVD background correction')
                        .replace('\n', ' ')
                    )
                    return False
                    
            logger.debug("DEBUG: All spectra have identical x-axes")
            
            # Construct data matrix (wavelengths x spectra)
            self.x_axis = first_x
            data_matrix = np.column_stack(y_scales)
            
            logger.debug(f"DEBUG: Data matrix shape: {data_matrix.shape}")
            
            # Compute SVD using standard numpy approach
            logger.debug("DEBUG: Running numpy SVD...")
            self.U, self.s, self.Vt = np.linalg.svd(data_matrix, full_matrices=False)
            
            self.corrected_U = self.U.copy()
            
            logger.debug(f"DEBUG: SVD complete - U: {self.U.shape}, s: {self.s.shape}, Vt: {self.Vt.shape}")
            
            # Calculate explained variance
            self.explained_variance = (self.s**2) / np.sum(self.s**2) * 100
            
            logger.debug(f"DEBUG: First 5 explained variances: {self.explained_variance[:5]}")
            
            # Clear any previous baseline corrections and inversion state
            self.baseline_corrections = {}
            self.baseline_points = {}
            self.baseline_settings = {}
            self.inverted_subspectra = set()
            
            logger.info("DEBUG: SVD computation successful")
            return True
            
        except Exception as e:
            logger.error(f"ERROR: SVD computation failed: {e}")
            logger.exception("Traceback:")
            return False

    def get_subspectrum(self, index):
        """Get original subspectrum by index."""
        if self.U is None or index >= self.U.shape[1]:
            return None, None
        return self.x_axis, self.U[:, index]
    
    def get_corrected_subspectrum(self, index):
        """Get baseline-corrected subspectrum by index."""
        if self.corrected_U is None or index >= self.corrected_U.shape[1]:
            return None, None
        return self.x_axis, self.corrected_U[:, index]
    
    def get_coefficients(self, index):
        """Get coefficients for specific subspectrum."""
        if self.Vt is None or index >= self.Vt.shape[0]:
            return None
        return self.Vt[index, :]
    
    def set_baseline_correction(self, subspectrum_index, baseline_points, baseline_fit_type='spline', poly_order=3):
        """
        Apply baseline correction to a subspectrum using user-defined points.
        
        Args:
            subspectrum_index: Index of subspectrum to correct
            baseline_points: List of (x, y) baseline point coordinates
            baseline_fit_type: 'spline' or 'poly' fitting method
            poly_order: Polynomial order for 'poly' type
            
        Returns:
            bool: True if baseline correction was applied successfully
        """
        if not baseline_points or len(baseline_points) < 2:
            return False
            
        # Store points exactly as provided - back to simple format
        self.baseline_points[subspectrum_index] = baseline_points.copy()
        self.baseline_settings[subspectrum_index] = {
            'type': baseline_fit_type,
            'order': poly_order
        }
        
        baseline = self._calculate_baseline(baseline_points, baseline_fit_type, poly_order)
        if baseline is None:
            return False
            
        self.baseline_corrections[subspectrum_index] = baseline.copy()
        if self.corrected_U is not None:
            self.corrected_U[:, subspectrum_index] = self.U[:, subspectrum_index] - baseline
            
        return True
    
    def _calculate_baseline(self, baseline_points, fit_type, poly_order):
        """Calculate baseline from points using specified fitting method."""
        if self.x_axis is None or len(baseline_points) < 2:
            return None
            
        try:
            # Sort points by x-coordinate
            sorted_points = sorted(baseline_points, key=lambda p: p[0])
            baseline_x, baseline_y = zip(*sorted_points)
            baseline_x, baseline_y = list(baseline_x), list(baseline_y)

            # CubicSpline requires strictly increasing x-values. Two points
            # placed very close together on the plot (easy to do with a
            # mouse click, especially when zoomed out) can map to identical
            # or near-identical x-coordinates, which would otherwise make
            # CubicSpline raise below and silently fall back to a
            # *different* fit type than the one actually selected -- this
            # is the rare "Spline behaves like Poly" case. Merging
            # near-duplicate x-values (averaging their y) up front removes
            # the underlying cause instead of just papering over its effect.
            dedup_x, dedup_y = [], []
            for x, y in zip(baseline_x, baseline_y):
                if dedup_x and np.isclose(x, dedup_x[-1]):
                    dedup_y[-1] = (dedup_y[-1] + y) / 2.0
                else:
                    dedup_x.append(x)
                    dedup_y.append(y)
            baseline_x, baseline_y = dedup_x, dedup_y

            if len(baseline_x) < 2:
                return None

            if fit_type == 'poly':
                # Polynomial fitting
                degree = min(len(baseline_x) - 1, poly_order)
                if degree >= 1:
                    coeffs = np.polyfit(baseline_x, baseline_y, degree)
                    baseline = np.polyval(coeffs, self.x_axis)
                else:
                    baseline = np.interp(self.x_axis, baseline_x, baseline_y)
            else:
                # Spline fitting (default)
                if len(baseline_x) >= 3:
                    try:
                        spline = interpolate.CubicSpline(baseline_x, baseline_y)
                        baseline = spline(self.x_axis)
                    except Exception as exc:
                        # Should be rare now that near-duplicate x-values are
                        # merged above, but fall back to linear interpolation
                        # rather than silently switching to a polynomial fit --
                        # linear is the closest fit-agnostic approximation, and
                        # won't be mistaken for the 'poly' option's potentially
                        # very different curve shape.
                        logger.warning(
                            "Spline baseline fit failed (%s); falling back to "
                            "linear interpolation for this baseline.", exc
                        )
                        baseline = np.interp(self.x_axis, baseline_x, baseline_y)
                else:
                    # Linear interpolation for 2 points
                    baseline = np.interp(self.x_axis, baseline_x, baseline_y)
                    
            return baseline
            
        except Exception as e:
            logger.error(f"Error calculating baseline: {e}")
            return None
    
    def clear_baseline(self, subspectrum_index):
        """Clear baseline correction for a subspectrum."""
        if subspectrum_index in self.baseline_corrections:
            del self.baseline_corrections[subspectrum_index]
        if subspectrum_index in self.baseline_points:
            del self.baseline_points[subspectrum_index]
        if subspectrum_index in self.baseline_settings:
            del self.baseline_settings[subspectrum_index]
            
        # Restore original subspectrum
        if self.corrected_U is not None and subspectrum_index < self.corrected_U.shape[1]:
            self.corrected_U[:, subspectrum_index] = self.U[:, subspectrum_index]
    
    def get_baseline_points(self, subspectrum_index):
        """Get baseline points for a subspectrum."""
        return self.baseline_points.get(subspectrum_index, [])
    
    def get_baseline_settings(self, subspectrum_index):
        """Get baseline settings for a subspectrum."""
        return self.baseline_settings.get(subspectrum_index, {'type': 'spline', 'order': 3})
    
    def reconstruct_spectra(self, original_spectra, progress_callback=None):
        """Reconstruct spectra using corrected subspectra based on current correction mode.

        progress_callback : optional callable, invoked every 50 spectra
            during the per-spectrum loop below — see
            SNIPBaselineManager.apply_correction for the full reasoning;
            same hook/contract. None (the default) — no change from
            before.
        """
        if self.corrected_U is None or not original_spectra:
            logger.debug("DEBUG: Cannot reconstruct - no corrected_U or no original spectra")
            return original_spectra
            
        try:
            logger.debug(f"DEBUG: Starting reconstruction with mode: {self.correction_mode}")
            
            # Determine which components to use for reconstruction
            if self.correction_mode == "selected":
                max_index = self.corrected_U.shape[1] - 1
                component_indices = [i for i in self.selected_subspectra if 0 <= i <= max_index]
                logger.debug(f"DEBUG: Using ONLY selected subspectra: {component_indices}")
                
            elif self.correction_mode == "corrected_only":
                component_indices = sorted(list(self.baseline_corrections.keys()))
                logger.debug(f"DEBUG: Using only corrected subspectra: {component_indices}")
                if not component_indices:
                    logger.warning("WARNING: No corrected subspectra available - using first component")
                    component_indices = [0]
                    
            elif self.correction_mode == "first_n":
                n_components = min(self.max_components, self.corrected_U.shape[1])
                component_indices = list(range(n_components))
                logger.debug(f"DEBUG: Using first {n_components} subspectra")
                
            elif self.correction_mode == "all_subspectra":
                n_components = self.corrected_U.shape[1]
                component_indices = list(range(n_components))
                logger.debug(f"DEBUG: Using all {n_components} subspectra")
                
            else:
                n_components = self.corrected_U.shape[1]
                component_indices = list(range(n_components))
                logger.debug(f"DEBUG: Using default (all) {n_components} subspectra")
            
            if not component_indices:
                logger.error("ERROR: No components selected for reconstruction")
                return original_spectra
            
            logger.debug(f"DEBUG: Reconstructing with components: {component_indices}")
            
            # Reconstruct data matrix using ONLY selected components
            original_data_matrix = np.column_stack([s['y_scale'] for s in original_spectra])
            
            logger.debug(f"DEBUG: Original data matrix shape: {original_data_matrix.shape}")
            
            # Always start with zeros and add ONLY the selected components
            reconstructed_matrix = np.zeros_like(original_data_matrix)
            
            for i in component_indices:
                # Use corrected subspectrum (which may be same as original if no baseline correction)
                subspectrum = self.corrected_U[:, i]
                # Use singular values in reconstruction: U * S * Vt
                coefficients = self.s[i] * self.Vt[i, :]
                contribution = np.outer(subspectrum, coefficients)
                reconstructed_matrix += contribution
                
                was_corrected = i in self.baseline_corrections
                logger.debug(f"DEBUG: Added contribution from component {i} (corrected: {was_corrected})")
            
            # Create new spectra with reconstructed data
            corrected_spectra = []
            for j, spectrum in enumerate(original_spectra):
                notify_progress(progress_callback, j)
                corrected_spectrum = {}
                
                # Copy all original spectrum data
                for key, value in spectrum.items():
                    if key in ['x_scale', 'y_scale']:
                        if hasattr(value, 'copy'):
                            corrected_spectrum[key] = value.copy()
                        else:
                            corrected_spectrum[key] = np.array(value)
                    elif key == 'metadata':
                        if hasattr(value, 'copy'):
                            corrected_spectrum[key] = value.copy()
                        else:
                            corrected_spectrum[key] = dict(value) if value else {}
                    else:
                        corrected_spectrum[key] = value
                
                # Store original y_scale if not already stored
                if 'original_y_scale' not in corrected_spectrum:
                    corrected_spectrum['original_y_scale'] = spectrum['y_scale'].copy()
                
                # Apply reconstructed data
                new_y_scale = reconstructed_matrix[:, j].copy()
                corrected_spectrum['y_scale'] = new_y_scale
                
                # Store SVD correction info in metadata
                if 'metadata' not in corrected_spectrum:
                    corrected_spectrum['metadata'] = {}
                
                original_y = spectrum['y_scale']
                orig_mean = float(np.mean(original_y))
                # Epsilon-guarded denominator — a spectrum whose mean is
                # legitimately at or near zero (signed techniques like CD/
                # ROA/VCD, or any derivative spectrum) would otherwise
                # divide by ~0 here, silently storing `inf` in metadata
                # (confirmed: raises a live numpy RuntimeWarning and
                # produces literal `inf`, which isn't even valid strict
                # JSON if this metadata is ever serialized that way).
                denom = abs(orig_mean) if abs(orig_mean) > 1e-12 else 1e-12
                corrected_spectrum['metadata']['svd_correction'] = {
                    # 'mode' (e.g. 'first_n', 'selected') intentionally
                    # NOT included — it's an internal setting name, not
                    # meaningful to a user, and subspectra_used_for_
                    # reconstruction below already shows the same thing
                    # in a more useful form (exactly which components,
                    # not which strategy picked them).
                    # Displayed to the user as-is (the metadata viewer
                    # title-cases dict keys directly), so these are stored
                    # 1-based ("Subspectrum 1", not "Subspectrum 0") —
                    # nothing downstream re-reads this list to index back
                    # into any array, it is a display/record-only field.
                    #
                    # Field order here is the display order (the metadata
                    # viewer shows dict fields in insertion order): which
                    # components were used, then what that did to the
                    # spectrum's overall level, then the two summary change
                    # metrics last.
                    'subspectra_used_for_reconstruction': [i + 1 for i in component_indices],
                    'total_subspectra_available': self.corrected_U.shape[1],
                    # Previously there were two separate fields here:
                    # 'baseline_corrections' (just len(...), a bare count)
                    # and 'corrected_subspectra' (the actual list the count
                    # was derived from) — the count added nothing the list
                    # didn't already show, so it's gone; the list is kept,
                    # renamed to make what it is unambiguous, and 1-based
                    # for the same reason as subspectra_used_for_reconstruction.
                    'baseline_corrected_subspectra': [i + 1 for i in sorted(self.baseline_corrections.keys())],
                    'original_mean': orig_mean,
                    'corrected_mean': float(np.mean(corrected_spectrum['y_scale'])),
                    'max_absolute_change': float(np.max(np.abs(original_y - new_y_scale))),
                    'relative_mean_change': float(abs(orig_mean - np.mean(new_y_scale)) / denom)
                }

                # NOTE: correction_history is intentionally NOT appended
                # here. reconstruct_spectra() is called repeatedly by the
                # dialog's live preview and Diagnostics button, every time
                # a setting is tweaked — not just on a real Apply. Appending
                # to correction_history here would add a fake "correction"
                # to the record on every preview redraw, not just real
                # applications. That accumulation correctly happens once,
                # in SVDBackgroundController.apply_svd_correction() (the
                # actual commit path) — see that method's own comment for
                # the full reasoning. This method stays a pure,
                # side-effect-free computation; 'svd_correction' above is
                # still set (the controller reads it via
                # meta.pop('svd_correction', ...) to build its own entry).
                
                corrected_spectra.append(corrected_spectrum)
            
            logger.info(f"DEBUG: Reconstruction completed successfully - returning {len(corrected_spectra)} spectra")
            return corrected_spectra
            
        except Exception as e:
            logger.error(f"ERROR: Exception during reconstruction: {e}")
            logger.exception("Traceback:")
            return original_spectra
    
    def get_correction_summary(self):
        """Get a summary of SVD correction settings."""
        if self.U is None:
            return {"status": "No SVD computed"}
        
        summary = {
            "status": "SVD computed",
            "n_subspectra": self.U.shape[1],
            "n_datapoints": self.U.shape[0],
            "correction_mode": self.correction_mode,
            "baseline_corrections": len(self.baseline_corrections),
            "explained_variance_first_5": self.explained_variance[:5].tolist() if self.explained_variance is not None else [],
            "inverted_subspectra": list(self.inverted_subspectra)
        }
        
        if self.correction_mode == "first_n":
            summary["max_components"] = self.max_components
        elif self.correction_mode == "selected":
            summary["selected_subspectra"] = self.selected_subspectra
        
        return summary