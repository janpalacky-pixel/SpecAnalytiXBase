# src/modules/data_analysis/batch_pipeline_manager.py
"""
Batch Pipeline Replay — the replay engine.

A pipeline is an ordered list of steps, each {'operation': <type
string>, 'settings': <settings dict>}. Given ANY selection of spectra,
run_pipeline() replays every step in order, feeding each step's output
spectra list in as the next step's input — exactly the same headless
computation each operation's own manager already does when its dialog's
Apply button is clicked, just chained together and driven from stored
settings instead of a dialog.

ELIGIBILITY — not every processing operation in this app can be
meaningfully captured into a reusable, portable pipeline. The operations
below were chosen because each is a pure, single-spectrum-in ->
single-spectrum-out transform driven entirely by a BATCH-SHARED settings
dict — the same settings dict applies identically to every spectrum in
whatever selection the pipeline is later run on, which is exactly the
"replay these settings elsewhere" contract a pipeline promises.

Deliberately EXCLUDED, and why:
  * Manual baseline — stateful: driven by per-spectrum (x, y) anchor
    points a user places by hand on THAT spectrum's own curve. A newly
    selected target spectrum has no matching points; there is nothing
    to "replay" against it.
  * CD Unit Conversion — its settings are keyed per-spectrum by identity
    (concentration, path length, molecular weight — physically tied to
    one specific sample) via a `per_spectrum` dict keyed by unique_id.
    Different target spectra are, in general, different samples with
    different concentrations; blindly replaying one sample's physical
    parameters onto another would silently produce wrong numbers rather
    than a genuine error, which is worse than not offering it at all.
  * SVD Background, SVD Interpolation, Interactive Subtraction, Combine
    Spectra, Spectral Calculator — each is fundamentally multi-spectrum
    (subtracts/combines/computes across a chosen set of OTHER spectra,
    or decomposes a basis from the whole current selection) rather than
    "apply this one settings dict to each spectrum independently". A
    pipeline step's settings can't meaningfully be replayed against an
    arbitrary different selection the same way SG smoothing's window
    length can.
  * X-axis alignment — aligns every spectrum to a chosen REFERENCE
    spectrum from the original selection; the same "which spectrum is
    the reference" ambiguity problem as Normalization's Reference mode
    (see below), without an equally cheap index-based workaround.

Two included operations carry a real caveat, documented rather than
worked around:
  * Normalization's "reference" mode designates the reference spectrum
    by its INDEX within whatever selection it's applied to
    (reference_spectrum_index) — replaying this step on a different or
    reordered selection uses whatever spectrum happens to sit at that
    index THEN, which may not be the one originally intended. This is
    surfaced explicitly in the Run Pipeline dialog and in the help doc.
  * Data Range / linearization only replays its BATCH-SHARED settings
    (ranges, is_exclude_mode, x_step, apply_linearization) — any
    per-spectrum range overrides recorded for the original spectra are
    not replayed, since they were keyed to those specific spectra's
    identities.
"""

from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match

logger = get_logger(__name__)


def _inner_cb(progress_callback):
    """Adapt run_pipeline's STEP-level progress_callback — called as
    progress_callback(done, total, label) once per pipeline step — into
    the no-argument callable each individual operation's own manager
    expects for ITS internal per-spectrum progress reporting (the
    established convention across this app, e.g.
    `lambda: QApplication.processEvents()` in every other controller's
    commit method). Calling the 3-arg step callback directly as a 0-arg
    callback from inside a manager's per-spectrum loop raises a
    TypeError — confirmed directly: "_progress() missing 3 required
    positional arguments" — since the two callback shapes are simply
    incompatible, not interchangeable. Returns None (meaning "no
    progress callback") if *progress_callback* itself is None, so a
    manager that skips calling it entirely when None behaves exactly as
    before.
    """
    if progress_callback is None:
        return None
    return lambda: None


def _run_snip(spectra, settings, progress_callback):
    from src.modules.data_analysis.snip_baseline_manager import SNIPBaselineManager
    return SNIPBaselineManager().apply_correction(spectra, settings, progress_callback=_inner_cb(progress_callback))


def _run_automated_baseline(spectra, settings, progress_callback):
    from src.modules.data_analysis.automated_baseline_manager import AutomatedBaselineManager
    return AutomatedBaselineManager().apply_correction(spectra, settings, progress_callback=_inner_cb(progress_callback))


def _run_normalization(spectra, settings, progress_callback):
    from src.modules.data_analysis.normalization_manager import NormalizationManager
    return NormalizationManager().normalize_spectra(spectra, settings, progress_callback=_inner_cb(progress_callback))


def _run_sg_smoothing(spectra, settings, progress_callback):
    from src.modules.data_analysis.savitzky_golay_manager import SavitzkyGolayManager
    # individual_delta_values (per-spectrum-label overrides) are meaningless
    # against a different selection — strip them, keep the shared settings.
    settings = {k: v for k, v in settings.items()
                if k not in ('delta_values', 'individual_delta_values')}
    return SavitzkyGolayManager().apply_sg_filter(spectra, settings, progress_callback=_inner_cb(progress_callback))


def _run_fft_denoising(spectra, settings, progress_callback):
    from src.modules.data_analysis.fft_denoising_manager import FFTDenoisingManager
    return FFTDenoisingManager().denoise_spectra(spectra, settings, progress_callback=_inner_cb(progress_callback))


def _run_cosmic_ray_removal(spectra, settings, progress_callback):
    from src.modules.data_analysis.cosmic_ray_manager import CosmicRayManager
    return CosmicRayManager().apply(
        spectra, threshold=settings.get('threshold'),
        replace_window=settings.get('replace_window'),
        progress_callback=_inner_cb(progress_callback),
    )


def _run_spike_removal(spectra, settings, progress_callback):
    from src.modules.data_analysis.spike_removal_manager import SpikeRemovalManager
    return SpikeRemovalManager().apply_automatic_removal(
        spectra, threshold=settings.get('threshold'), half_window=settings.get('half_window'),
    )


def _run_resolution_enhancement(spectra, settings, progress_callback):
    from src.modules.data_analysis.resolution_enhancement_manager import ResolutionEnhancementManager
    return ResolutionEnhancementManager().enhance(
        spectra, irf_sigma=settings.get('irf_sigma'), snr=settings.get('snr'),
        progress_callback=_inner_cb(progress_callback),
    )


def _run_xaxis_unit_conversion(spectra, settings, progress_callback):
    from src.modules.data_analysis.xaxis_unit_conversion_manager import XAxisUnitConversionManager
    return XAxisUnitConversionManager().convert_spectra(spectra, settings, progress_callback=_inner_cb(progress_callback))


def _run_data_range(spectra, settings, progress_callback):
    from src.modules.data_analysis.spectral_range_manager import SpectralRangeManager
    # Only batch-shared settings are ever stored for a pipeline step (see
    # module docstring) — no per-spectrum override dicts exist here to
    # accidentally carry over.
    mgr = SpectralRangeManager()
    mgr.update_settings(settings)
    return mgr.apply_ranges_to_spectra(spectra)


# Registry: operation type string -> {'run', 'min_spectra',
# 'requires_common_x_axis', 'label'}. 'run' always has the signature
# (spectra, settings, progress_callback) -> list[spectrum_dict], hiding
# each manager's own real method name/signature (see module docstring —
# they vary quite a bit: some take a settings dict directly, some need
# update_settings() called first, some take plain kwargs).
ELIGIBLE_OPERATIONS = {
    'SNIP Baseline': {
        'run': _run_snip, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'Automated Baseline': {
        'run': _run_automated_baseline, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'Normalization': {
        'run': _run_normalization, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'SG-smoothing': {
        'run': _run_sg_smoothing, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'FFT Denoising': {
        'run': _run_fft_denoising, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'Cosmic ray removal': {
        'run': _run_cosmic_ray_removal, 'min_spectra': 2, 'requires_common_x_axis': True,
    },
    'Spike removal': {
        'run': _run_spike_removal, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'Resolution enhancement': {
        'run': _run_resolution_enhancement, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'X-axis Unit Conversion': {
        'run': _run_xaxis_unit_conversion, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
    'Data range': {
        'run': _run_data_range, 'min_spectra': 1, 'requires_common_x_axis': False,
    },
}

# Operations that DO write a correction_history entry / get committed via
# Apply, but are deliberately not pipeline-eligible — used purely to give
# a precise, per-operation reason in the UI (e.g. greyed out with a
# tooltip) rather than a generic "not supported".
INELIGIBLE_REASONS = {
    'Manual baseline': "Stateful: baseline points are placed by hand on one "
                        "specific spectrum's curve — a new target spectrum has no matching points.",
    'CD Unit Conversion': "Settings (concentration, path length, molecular weight) are "
                           "tied to one specific sample — replaying them on a different "
                           "spectrum would silently apply the wrong sample's physical parameters.",
    'SVD background': "Multi-spectrum: decomposes a basis from the whole selection it was run on, "
                       "not a per-spectrum settings dict that can be replayed elsewhere.",
    'SVD Interpolation': "Multi-spectrum: interpolates across the whole selection it was run on.",
    'Interactive subtraction': "Multi-spectrum: subtracts specific OTHER chosen spectra, "
                                "not a settings dict that applies independently per spectrum.",
    'Combine Spectra': "Multi-spectrum: combines specific chosen source spectra into one result.",
    'Spectral Calculator': "Multi-spectrum: the formula references specific chosen spectra by name.",
    'X-axis alignment': "Aligns every spectrum to one reference spectrum from the original "
                         "selection — the same reference wouldn't exist, or wouldn't be the "
                         "right one, in an arbitrary different selection.",
}

# Steps whose settings depend on WHICH spectrum sits at a given position
# within the selection they're run on (rather than being fully
# self-contained) — surfaced as a caveat in the Run Pipeline dialog, not
# blocked outright (see module docstring).
INDEX_SENSITIVE_MODES = {
    'Normalization': lambda settings: settings.get('normalization_mode') == 'reference'
                      or settings.get('reference_spectrum_index') is not None,
}


class PipelineStepError(Exception):
    """Raised by run_pipeline() when a step can't be run against the
    current spectra — carries the 1-based step index and operation name
    so the caller can report exactly where the run stopped."""

    def __init__(self, step_index, operation, message):
        self.step_index = step_index
        self.operation = operation
        super().__init__(f"Step {step_index} ({operation}): {message}")


class BatchPipelineManager:
    """Pure computation — validates and replays a pipeline's steps
    against a spectra list. Never touches the UI; never mutates its
    inputs (every underlying manager already returns fresh spectrum
    dicts, so this class simply chains their outputs together)."""

    @staticmethod
    def is_eligible(operation_type: str) -> bool:
        return operation_type in ELIGIBLE_OPERATIONS

    @staticmethod
    def ineligible_reason(operation_type: str) -> str:
        return INELIGIBLE_REASONS.get(
            operation_type, "This operation isn't a self-contained, single-spectrum "
                            "settings-driven transform, so it can't be replayed as a pipeline step.")

    @staticmethod
    def is_index_sensitive(operation_type: str, settings: dict) -> bool:
        check = INDEX_SENSITIVE_MODES.get(operation_type)
        return bool(check and check(settings or {}))

    def _validate_step(self, operation_type, settings, spectra):
        spec = ELIGIBLE_OPERATIONS.get(operation_type)
        if spec is None:
            return f"'{operation_type}' is not a pipeline-eligible operation."
        if len(spectra) < spec['min_spectra']:
            return (f"needs at least {spec['min_spectra']} spectra "
                    f"(the current selection has {len(spectra)}).")
        if spec['requires_common_x_axis'] and len(spectra) >= 2:
            x_ref = spectra[0].get('x_scale')
            for s in spectra[1:]:
                if not axes_match(x_ref, s.get('x_scale')):
                    return "requires all spectra to share one identical x-axis."
        return None

    def run_pipeline(self, spectra: list, steps: list, progress_callback=None) -> list:
        """Replay *steps* in order against *spectra*. Returns the final
        output spectra list. Raises PipelineStepError, naming the exact
        step, if any step's precondition isn't met or its manager raises
        — the run is atomic: nothing already-applied is rolled back
        automatically, but the caller is told precisely where it stopped
        so partial progress is never silently mistaken for a full run.
        """
        current = list(spectra)
        total = len(steps)
        for i, step in enumerate(steps, start=1):
            operation = step.get('operation')
            settings = step.get('settings') or {}

            error = self._validate_step(operation, settings, current)
            if error:
                raise PipelineStepError(i, operation, error)

            if progress_callback:
                try:
                    progress_callback(i - 1, total, f"Step {i}/{total}: {operation}")
                except Exception:
                    # A broken progress display must not stop the pipeline.
                    logger.warning("Pipeline progress callback failed", exc_info=True)

            spec = ELIGIBLE_OPERATIONS[operation]
            try:
                current = spec['run'](current, settings, progress_callback)
            except PipelineStepError:
                raise
            except Exception as exc:
                raise PipelineStepError(i, operation, str(exc)) from exc

        if progress_callback:
            try:
                progress_callback(total, total, "Done")
            except Exception:
                logger.warning("Pipeline progress callback failed", exc_info=True)
        return current

    @staticmethod
    def describe_step(step: dict) -> str:
        """One-line human-readable summary of a step's settings, for
        display in the Save/Run pipeline dialogs — reuses the same
        formatter IncrementalOperationsManager already has for the
        Operations History dialog, so the text matches exactly what the
        user already saw when they originally ran the operation."""
        from src.modules.data_analysis.incremental_operations_manager import IncrementalOperationsManager
        operation = step.get('operation')
        settings = step.get('settings') or {}
        dummy = IncrementalOperationsManager()
        dummy.operations_chain = [{'type': operation, 'parameters': settings}]
        text = dummy.get_formatted_parameters(0)
        return text.replace('\n', '  ') if text else '(no parameters)'
