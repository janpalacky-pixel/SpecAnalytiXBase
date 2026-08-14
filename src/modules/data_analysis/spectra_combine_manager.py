# src/modules/data_analysis/spectra_combine_manager.py

import numpy as np
from datetime import datetime
from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch, find_axis_mismatch
from src.modules.utils.correction_history import append_correction_history

class CombineSpectraManager:
    """Business logic for spectra combine operations like averaging and summing."""

    def validate(self, spectra: list) -> str:
        """Check preconditions before attempting the real calculation.
        Returns an error message string, or None if everything is fine.
        Used both by perform_operation (as a guard) and by the dialog's
        live preview, so the user gets the same clear message either way
        instead of a numpy shape-mismatch traceback."""
        if not spectra or len(spectra) < 2:
            return "Select at least two spectra to combine."

        # Uses the shared, tolerance-aware comparison (spectra_validation.
        # axes_match / find_axis_mismatch) rather than a bare np.allclose().
        # np.allclose's DEFAULT rtol is 1e-5 -- on a 1000 cm-1 axis that's a
        # tolerance of ~0.01 cm-1, loose enough to accept two genuinely
        # different grids as "identical" and then average/sum them
        # point-by-point as if point i of one spectrum really were the same
        # x location as point i of the other. axes_match scales the
        # tolerance to the data instead (one millionth of the median step),
        # far below any real instrument's precision but far above float
        # round-off, so a length-matched-but-actually-different grid is
        # correctly rejected instead of silently mispaired.
        mismatch = find_axis_mismatch(spectra)
        if mismatch is not None:
            ref, other = mismatch
            return describe_axis_mismatch(ref, other, 'Combine Spectra')
        return None

    def perform_operation(self, spectra: list, operation_type: str) -> dict:
        """
        Performs an combine operation on a list of spectra.

        Args:
            spectra: A list of spectrum dictionaries. Assumes all have identical x-axes.
            operation_type: The operation to perform ('average' or 'sum').

        Returns:
            A new spectrum dictionary representing the result.
        """
        error = self.validate(spectra)
        if error:
            raise ValueError(error)

        # Extract all y-scales
        y_scales = [s['y_scale'] for s in spectra]
        
        # Stack into a 2D numpy array (each row is a spectrum's y-data)
        y_matrix = np.vstack(y_scales)

        # Perform the calculation
        if operation_type == 'average':
            result_y = np.mean(y_matrix, axis=0)
            # ddof=1 -> sample standard deviation (divide by N-1), not the
            # numpy default of population std (divide by N). The replicates
            # being combined here are a SAMPLE of the underlying
            # measurement variability, not the entire population of
            # possible measurements, so N-1 is the standard convention for
            # "how much did my replicates vary" (matches Excel STDEV,
            # Origin, GraphPad, etc.). This matters most at exactly the N
            # this feature is most often used with: with only 2 replicates,
            # population std understates the band by a factor of sqrt(2)
            # compared to sample std. Safe here since validate() already
            # requires at least 2 spectra, so N-1 >= 1.
            result_std = np.std(y_matrix, axis=0, ddof=1)
        elif operation_type == 'sum':
            result_y = np.sum(y_matrix, axis=0)
            result_std = None  # variance around a sum isn't a meaningful quantity
        else:
            raise ValueError(f"Unknown operation type: {operation_type}")

        # Use the x-scale from the first spectrum (since they are all identical)
        result_x = spectra[0]['x_scale'].copy()
        
        # Create metadata for the new spectrum
        source_labels = [s['label'] for s in spectra]
        metadata = {
            'creation_method': operation_type,
            'source_spectra_count': len(spectra),
            'source_spectra': source_labels,
            'creation_timestamp': datetime.now().isoformat()
        }

        result = {
            'x_scale': result_x,
            'y_scale': result_y,
            'label': "new_spectrum",  # Placeholder, will be named in controller
            'metadata': metadata
        }
        # Shared, chronologically-ordered history mechanism (see
        # correction_history.py) — started fresh here since this is a
        # brand-new spectrum with no prior history of its own; any later
        # operation applied to it (e.g. a baseline correction) will find
        # this entry already present via its own metadata.get('correction_history')
        # and append after it, giving one unified timeline.
        result['metadata']['correction_history'] = append_correction_history(
            None, 'Combine Spectra',
            {
                'operation_type': operation_type,
                'source_spectra': source_labels,
                'source_spectra_count': len(spectra),
            }
        )
        if result_std is not None:
            # Kept as a separate top-level key (not inside metadata, which
            # is meant for small descriptive values) since this is a full
            # array the same length as y_scale, used by the dialog's
            # preview to draw a shaded +/-1 std-dev band. Saving this
            # spectrum normally ignores unknown keys, same as 'metadata'.
            result['y_std'] = result_std
        return result