# src/modules/data_analysis/interactive_subtraction_manager.py
import numpy as np

from src.modules.utils.spectra_validation import axes_match, describe_axis_mismatch
from src.modules.utils.correction_history import append_correction_history


class AxisMismatchError(ValueError):
    """Raised when an operation that requires a common x-axis is given
    spectra that don't have one. Callers (controller/dialog) catch this
    and turn it into a user-facing message — the manager itself has no
    Qt, so it never shows a dialog directly."""
    pass


class InteractiveSubtractionManager:
    """Business logic for interactive subtraction operations on spectra."""

    def __init__(self):
        self.subtraction_factor = 1.0
        self.minuend_indices = []
        self.subtrahend_index = None

        # Persistent storage keyed by (minuend_key, subtrahend_key) — see
        # _key_for() — so factors survive dialog close/reopen for the same
        # selection. Cleared by the controller when the main-window
        # selection changes.
        self.stored_factors: dict = {}   # {(minuend_key, subtrahend_key): factor}

        # Spectra loaded from an external file to use as a subtrahend.
        # Local to this controller/session only — never added to the main
        # spectrum list — but survives dialog close/reopen, the same way
        # stored_factors does.
        self.file_subtrahends: list = []

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum key for stored_factors — uses the spectrum's
        persistent unique_id rather than its label. Labels are not stable
        identifiers: renaming a spectrum doesn't change its identity, and
        two unrelated spectra (e.g. from separate import sessions, or a
        re-imported file producing the same filename-derived label) can end
        up sharing a label even though they've never had anything to do
        with each other. Falls back to label only if a spectrum genuinely
        has no unique_id.

        NOTE: file-loaded subtrahends are now given a synthetic unique_id
        at import time (see InteractiveSubtractionDialog.on_import_subtrahend_clicked),
        specifically so they never fall into the label-fallback branch here
        and risk colliding with an unrelated main-window spectrum that
        happens to share the same label. The fallback below only exists for
        legacy/defensive purposes.

        Every read/write of stored_factors must go through this helper —
        never index it with a raw spectrum['label'] directly."""
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum['label']

    def prune_to_current_spectra(self, current_spectra):
        """Remove stored factors whose minuend or subtrahend key no longer
        matches a spectrum that's actually around right now (checked
        against current_spectra plus this manager's own file_subtrahends).
        Without this, a renamed/removed/re-imported spectrum can orphan a
        stored factor or, worse, have an unrelated re-imported spectrum
        silently inherit one (see _key_for)."""
        current_keys = {self._key_for(s) for s in current_spectra}
        current_keys |= {self._key_for(s) for s in self.file_subtrahends}
        for key in list(self.stored_factors.keys()):
            m_key, s_key = key
            if m_key not in current_keys or s_key not in current_keys:
                del self.stored_factors[key]

    def subtract_spectra(self, spectra, minuend_indices, subtrahend, subtraction_factor):
        """
        Subtract a scaled subtrahend spectrum from selected minuend spectra.

        Requires every targeted minuend to share the subtrahend's exact
        x-axis (within the shared axes_match tolerance). This is a
        point-by-point operation — minuend[i] - factor * subtrahend[i] —
        so there is no meaningful way to do it across different grids
        without inventing data. If the axes don't match, this refuses
        rather than silently interpolating: use the Data Range operation
        to put the spectra on a common axis first, or the dialog's
        explicit "Align to Minuend X-Axis" action for a file-loaded
        subtrahend.

        Args:
            spectra: List of all spectrum dictionaries
            minuend_indices: Indices of spectra to subtract from
            subtrahend: Subtrahend spectrum dictionary
            subtraction_factor: Factor to multiply subtrahend by

        Returns:
            List of spectra with subtraction applied

        Raises:
            AxisMismatchError: if any targeted minuend's x-axis doesn't
                match the subtrahend's.
        """
        result_spectra = []

        subtrahend_x = subtrahend['x_scale'].copy()
        subtrahend_y = subtrahend['y_scale'].copy()

        for i, spectrum in enumerate(spectra):
            # Create a copy of the spectrum
            result_spectrum = {}
            for key, value in spectrum.items():
                if key in ['x_scale', 'y_scale']:
                    result_spectrum[key] = value.copy() if hasattr(value, 'copy') else value
                elif key == 'metadata':
                    result_spectrum[key] = value.copy() if hasattr(value, 'copy') else value
                else:
                    result_spectrum[key] = value

            # Only subtract if this spectrum is in minuend_indices
            if i in minuend_indices:
                minuend_x = spectrum['x_scale'].copy()
                minuend_y = spectrum['y_scale'].copy()

                if not axes_match(minuend_x, subtrahend_x):
                    raise AxisMismatchError(describe_axis_mismatch(
                        spectrum, subtrahend, 'Interactive subtraction'))

                result_y = minuend_y - (subtraction_factor * subtrahend_y)

                # Update y_scale with subtraction result
                result_spectrum['y_scale'] = result_y

                # Shared, chronologically-ordered history across every
                # operation type that records one (see
                # correction_history.py). Guard for a spectrum with no
                # 'metadata' key at all. This used to ALSO be written as a
                # separate top-level spectrum['subtraction_info'] key
                # holding the exact same dict — nothing in the codebase
                # ever read that key (confirmed by search), so it was
                # pure dead weight carried on every subtracted spectrum;
                # removed (same cleanup as automated_baseline_manager's
                # equivalent dead 'auto_baseline_correction' key).
                if 'metadata' not in result_spectrum or result_spectrum['metadata'] is None:
                    result_spectrum['metadata'] = {}
                result_spectrum['metadata']['correction_history'] = append_correction_history(
                    spectrum.get('metadata'), 'Interactive subtraction',
                    {
                        'subtrahend_label': subtrahend['label'],
                        'subtrahend_key': self._key_for(subtrahend),
                        'subtraction_factor': subtraction_factor,
                        'subtracted': True,
                    }
                )

            result_spectra.append(result_spectrum)

        return result_spectra

    def subtract_one(self, minuend, subtrahend, subtraction_factor):
        """Apply a single (minuend, subtrahend, factor) triple to one
        spectrum and return the result. Reuses subtract_spectra's existing
        copy/metadata logic by wrapping the single minuend in a
        one-element list, rather than duplicating that logic here.

        Raises:
            AxisMismatchError: if the two spectra don't share an x-axis.
        """
        result = self.subtract_spectra([minuend], [0], subtrahend, subtraction_factor)
        return result[0]

    def estimate_initial_factor(self, minuend, subtrahend):
        """
        Estimate an initial subtraction factor as the least-squares scalar
        that best matches the subtrahend to the minuend — i.e. the factor f
        that minimizes ||minuend - f * subtrahend||^2. This has a closed
        form (the projection of minuend onto subtrahend):

            f = (minuend . subtrahend) / (subtrahend . subtrahend)

        This replaces an earlier SVD/PCA-loadings-ratio heuristic that (a)
        was solving a different problem (shared-variance decomposition,
        not "best scalar to subtract") and (b) took abs() of the result,
        which silently forced the estimate positive. That's wrong for
        signed techniques (CD/ROA/VCD, and anywhere a feature is genuinely
        anti-correlated with the reference) where the correct starting
        factor can legitimately be negative. The least-squares projection
        used here has no such bias: it returns whatever sign actually
        minimizes the residual.

        Args:
            minuend: Minuend spectrum dictionary
            subtrahend: Subtrahend spectrum dictionary

        Returns:
            Estimated subtraction factor (float)

        Raises:
            AxisMismatchError: if the two spectra don't share an x-axis.
        """
        minuend_x = minuend['x_scale']
        minuend_y = minuend['y_scale']
        subtrahend_x = subtrahend['x_scale']
        subtrahend_y = subtrahend['y_scale']

        if not axes_match(minuend_x, subtrahend_x):
            raise AxisMismatchError(describe_axis_mismatch(
                minuend, subtrahend, 'Interactive subtraction'))

        denom = float(np.dot(subtrahend_y, subtrahend_y))
        if denom <= 1e-300 or not np.isfinite(denom):
            # All-zero (or degenerate) subtrahend: no meaningful scale to
            # estimate. 1.0 is an arbitrary-but-harmless default — there is
            # no "correct" factor when the subtrahend carries no signal.
            return 1.0

        factor = float(np.dot(minuend_y, subtrahend_y)) / denom
        if not np.isfinite(factor):
            return 1.0
        return factor

    def preview_difference(self, minuend, subtrahend, subtraction_factor):
        """Compute (x, minuend_y, scaled_subtrahend_y, diff_y) for live
        preview — used by the dialog's plot and nowhere else. This is the
        SINGLE place that decides what "preview a subtraction" means, so
        the dialog doesn't carry its own second copy of the axis check /
        math (previously it had two: one in update_plot, one in
        estimate_and_set_initial_factor — both silently interpolating on
        mismatch, independently of this manager's own copy of the same
        bug).

        Raises:
            AxisMismatchError: if the two spectra don't share an x-axis.
            Callers must catch this and show a non-destructive "can't
            preview" state rather than compute anything.
        """
        minuend_x = minuend['x_scale']
        minuend_y = minuend['y_scale']
        subtrahend_x = subtrahend['x_scale']
        subtrahend_y = subtrahend['y_scale']

        if not axes_match(minuend_x, subtrahend_x):
            raise AxisMismatchError(describe_axis_mismatch(
                minuend, subtrahend, 'Interactive subtraction'))

        scaled = subtraction_factor * subtrahend_y
        diff = minuend_y - scaled
        return minuend_x, minuend_y, scaled, diff

    def clear_stored_factors(self):
        """Clear all stored factors — called when the main-window selection changes."""
        self.stored_factors.clear()

    def update_settings(self, settings):
        """Update subtraction settings."""
        if 'subtraction_factor' in settings:
            self.subtraction_factor = settings['subtraction_factor']
        if 'minuend_indices' in settings:
            self.minuend_indices = settings['minuend_indices']
        if 'subtrahend_index' in settings:
            self.subtrahend_index = settings['subtrahend_index']
