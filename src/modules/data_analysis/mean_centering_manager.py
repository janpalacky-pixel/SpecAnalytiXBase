# src/modules/data_analysis/mean_centering_manager.py
"""
Business logic for ensemble mean-centering: subtract the AVERAGE SPECTRUM
of a selected batch (the per-wavelength mean, computed across all
selected spectra) from every spectrum in that batch.

This is the exact same preprocessing step the PCA / SVD Scores & Loadings
and SVD Analysis dialogs perform internally when their "Mean-center
spectra before SVD" checkbox is on (see PcaScoresManager.compute_svd,
SVDAnalysisManager.compute_svd_from_spectra,
SVDBackgroundManager.compute_svd_from_spectra — all three compute
``mean_spectrum = data_matrix.mean(axis=1)`` and subtract it before
``np.linalg.svd``). This module exposes that one step as its own
standalone, reusable operation, independent of running any decomposition
— e.g. to visually inspect per-wavelength deviations from the ensemble
average directly, or to export pre-centered data for use elsewhere.

NOT THE SAME AS Normalization's "Mean Centering" / "Z-score" modes
--------------------------------------------------------------------
Normalization's per-spectrum modes (see normalization_manager.py's
``_normalize_mean_centering`` / ``_normalize_z_score``) subtract a
spectrum's OWN scalar mean from itself — a row-wise operation where every
spectrum is processed completely independently of every other one, same
as every other Normalization mode. This is fundamentally different: it
subtracts the ENSEMBLE average spectrum (one vector, shared across the
whole batch, computed from ALL of them together) — a column-wise,
whole-dataset operation where every output depends on every spectrum in
the selection, not just itself. See pca_scores_help.py's "Technical
background" section for the full mathematical rationale (why this
particular centering makes SVD components uncorrelated, not just
orthogonal, and why per-wavelength standardization is deliberately NOT
offered anywhere in this application).

REQUIRES A SHARED X-AXIS, same requirement as SVD/PCA — averaging is a
per-wavelength operation and is only meaningful when every spectrum in
the batch reports the same wavelengths.
"""
import numpy as np

from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)


class MeanCenteringManager:
    """Ensemble mean-centering — subtract the average spectrum of a
    selected batch from every spectrum in that batch.

    Unlike Normalization/CD/X-axis Unit Conversion, there are no tunable
    numeric parameters (no region, no reference spectrum, no physical
    constant) — the only setting is whether to also emit the computed
    mean spectrum itself as an extra output, for inspection/QC.
    """

    def __init__(self):
        self.include_mean_spectrum = False
        # Populated by the most recent compute_centered_spectra() call —
        # read by the controller/dialog for messages and the optional
        # extra "mean spectrum" output.
        self.last_mean_x = None
        self.last_mean_y = None
        self.last_source_labels = []

    def update_settings(self, settings):
        if 'include_mean_spectrum' in settings:
            self.include_mean_spectrum = bool(settings['include_mean_spectrum'])

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @staticmethod
    def validate_shared_x_axis(spectra):
        """Raise ValueError with a clear, actionable message if the
        selected spectra don't all share an identical x-axis — same
        requirement, and same style of check, as
        SVDAnalysisController.show_dialog's upfront validation."""
        if len(spectra) < 1:
            return
        first_x = np.asarray(spectra[0]['x_scale'], dtype=float)
        for spectrum in spectra[1:]:
            x = np.asarray(spectrum['x_scale'], dtype=float)
            if len(x) != len(first_x) or not np.allclose(x, first_x, rtol=1e-7, atol=1e-9):
                raise ValueError(
                    "Cannot mean-center: spectra have different x-axes.\n\n"
                    f"First spectrum ('{spectra[0]['label']}'): {len(first_x)} points "
                    f"({first_x[0]:.4g} to {first_x[-1]:.4g})\n"
                    f"Spectrum '{spectrum['label']}': {len(x)} points "
                    f"({x[0]:.4g} to {x[-1]:.4g})\n\n"
                    "Please select only spectra with identical x-axes."
                )

    # ------------------------------------------------------------------
    # Core computation
    # ------------------------------------------------------------------
    def compute_centered_spectra(self, spectra, settings=None, progress_callback=None):
        """Subtract the ensemble average spectrum from every spectrum in
        *spectra*. Returns a new list of centered spectrum dicts — inputs
        are never mutated.

        progress_callback: optional callable, invoked every 50 spectra —
        same hook/contract as every other manager in this codebase (see
        progress_utils.notify_progress). None (the default) — no change.

        Raises ValueError (via validate_shared_x_axis) if the spectra
        don't share an identical x-axis.
        """
        if settings:
            self.update_settings(settings)

        valid = [s for s in spectra if len(s.get('x_scale', [])) > 0 and len(s.get('y_scale', [])) > 0]
        if not valid:
            self.last_mean_x = None
            self.last_mean_y = None
            self.last_source_labels = []
            return []

        self.validate_shared_x_axis(valid)

        x_scale = np.asarray(valid[0]['x_scale'], dtype=float)
        # data_matrix: rows = wavelengths, columns = spectra — identical
        # layout/convention to PcaScoresManager / SVDAnalysisManager /
        # SVDBackgroundManager's compute_svd_from_spectra.
        data_matrix = np.column_stack([np.asarray(s['y_scale'], dtype=float) for s in valid])
        mean_spectrum = data_matrix.mean(axis=1)

        self.last_mean_x = x_scale
        self.last_mean_y = mean_spectrum
        self.last_source_labels = [s.get('label', '?') for s in valid]

        n = len(valid)
        centered_spectra = []
        for i, spectrum in enumerate(valid):
            notify_progress(progress_callback, i)
            centered = spectrum.copy()
            centered['x_scale'] = x_scale.copy()
            centered['y_scale'] = data_matrix[:, i] - mean_spectrum

            info = {
                'n_spectra_averaged': n,
                'source_labels': list(self.last_source_labels),
            }
            centered['mean_centering_info'] = info

            # spectrum.copy() above is a SHALLOW copy — centered['metadata']
            # would still be the exact same dict object as the source
            # spectrum's metadata unless replaced here, which would
            # silently mutate the original too (same fix applied in every
            # other manager in this app).
            centered['metadata'] = dict(centered.get('metadata') or {})
            centered['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'Mean-Center Spectra (Dataset)', info
            )

            centered_spectra.append(centered)

        return centered_spectra

    def get_mean_spectrum(self):
        """Return (x, y, source_labels) for the ensemble mean computed by
        the most recent compute_centered_spectra() call, or (None, None,
        []) if none has run yet."""
        return self.last_mean_x, self.last_mean_y, list(self.last_source_labels)
