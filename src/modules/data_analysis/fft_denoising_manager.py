# src/modules/data_analysis/fft_denoising_manager.py
"""
FFT Denoising manager.

Filters a spectrum in the frequency domain by zeroing (or windowing)
specified frequency bands, then reconstructing via inverse FFT.

The MATLAB fnoise.m code worked on a normalised frequency axis
f ∈ [0, 1] where 0 is DC and 1 is the Nyquist frequency.  Python's
numpy.fft uses the same convention internally; we expose the same
normalised-frequency scale to the user.

Filter definition
─────────────────
Each *band* is a (f_low, f_high) pair on the normalised scale [0, 1].
Frequencies inside the band are zeroed in the complex spectrum (hard
rectangular filter, i.e. ideal band-stop).  Multiple bands can be
combined; their union is zeroed.

Convenience presets
───────────────────
• low_cutoff  – zero all frequencies BELOW this value
  → removes slowly-varying baseline contributions
• high_cutoff – zero all frequencies ABOVE this value
  → removes high-frequency electronic noise
Together they implement a band-pass filter.

The two approaches (band list + scalar cutoffs) can be mixed: the
manager merges them into one combined mask before reconstruction.
"""

import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.correction_history import append_correction_history

logger = get_logger(__name__)


class FFTDenoisingManager:
    """Business logic for FFT-based spectral denoising."""

    def __init__(self):
        # List of (f_low, f_high) stop-bands on the normalised [0,1] scale
        self.stop_bands: list[tuple[float, float]] = []

        # Scalar convenience cutoffs (None = disabled)
        self.low_cutoff:  float | None = None   # remove DC / baseline (f < low_cutoff)
        self.high_cutoff: float | None = None   # remove HF noise      (f > high_cutoff)

        # Window function applied to the *pass* region before IFFT
        # 'none' = rectangular (hard), 'hann' = Hann window on transition edges
        self.window: str = 'none'

        # Labels of any spectra that failed to denoise on the most recent
        # denoise_spectra() call (left unchanged, original data returned)
        # — see that method.
        self.failed_labels: list = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def denoise_spectra(self, spectra: list, settings: dict, progress_callback=None) -> list:
        """Apply FFT denoising to every spectrum in *spectra*.

        Returns a new list; originals are not modified. A spectrum that
        fails to denoise (e.g. an unexpected numerical issue) is returned
        UNCHANGED rather than dropped or corrupted — see self.failed_labels
        for which ones, so the caller can surface this to the user instead
        of it being visible only in the log.

        progress_callback : optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before.
        """
        self.update_settings(settings)
        self.failed_labels = []
        result = []
        for i, s in enumerate(spectra):
            notify_progress(progress_callback, i)
            try:
                result.append(self._process_one(s))
            except Exception as exc:
                logger.warning("FFT denoising failed for '%s': %s", s.get('label', '?'), exc)
                self.failed_labels.append(s.get('label', '?'))
                result.append(s)   # return original on failure
        return result

    def update_settings(self, settings: dict):
        if 'stop_bands' in settings:
            self.stop_bands = list(settings['stop_bands'])
        if 'low_cutoff' in settings:
            self.low_cutoff = settings['low_cutoff']
        if 'high_cutoff' in settings:
            self.high_cutoff = settings['high_cutoff']
        if 'window' in settings:
            self.window = settings['window']

    def compute_power_spectrum(self, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (frequencies, power_spectrum) for preview plots.

        Frequencies are on the normalised one-sided scale [0, 1].
        Power is the single-sided amplitude spectrum.
        """
        n  = len(y)
        Y  = np.fft.rfft(y)
        f  = np.fft.rfftfreq(n)          # 0 … 0.5
        f  = f / f[-1]                   # normalise to [0, 1]
        amp = np.abs(Y) * 2.0 / n
        amp[0] /= 2.0                    # DC needs no doubling
        return f, amp

    def preview_denoised(self, y: np.ndarray) -> np.ndarray:
        """Return the denoised y-array for a single spectrum (no copy overhead)."""
        return self._filter_signal(y)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_one(self, spectrum: dict) -> dict:
        y = np.asarray(spectrum['y_scale'], dtype=float)
        y_new = self._filter_signal(y)

        out = {}
        for k, v in spectrum.items():
            if isinstance(v, np.ndarray):
                out[k] = v.copy()
            elif isinstance(v, dict):
                out[k] = {ki: vi.copy() if isinstance(vi, np.ndarray) else vi
                          for ki, vi in v.items()}
            else:
                out[k] = v

        out['y_scale'] = y_new
        # Shared, chronologically-ordered history across every operation
        # type that records one (see correction_history.py).
        # out['metadata'] is already a fresh copy (dict.copy() in the loop
        # above), not shared with the source spectrum. This used to ALSO
        # be written as a separate top-level spectrum['fft_denoising_info']
        # key holding the exact same dict — nothing in the codebase ever
        # read that key (confirmed by search), so it was pure dead weight
        # carried on every denoised spectrum; removed (same cleanup as
        # automated_baseline_manager's equivalent dead
        # 'auto_baseline_correction' key).
        if 'metadata' not in out or out['metadata'] is None:
            out['metadata'] = {}
        out['metadata']['correction_history'] = append_correction_history(
            spectrum.get('metadata'), 'FFT Denoising',
            {
                'stop_bands':   list(self.stop_bands),
                'low_cutoff':   self.low_cutoff,
                'high_cutoff':  self.high_cutoff,
                'window':       self.window,
            }
        )
        return out

    def _filter_signal(self, y: np.ndarray) -> np.ndarray:
        """Core FFT filter: zero selected frequency bands, return IFFT."""
        n   = len(y)
        Y   = np.fft.rfft(y)
        f   = np.fft.rfftfreq(n)          # 0 … 0.5
        f_n = f / f[-1] if f[-1] > 0 else f   # normalise to [0, 1]

        mask = np.ones(len(Y), dtype=float)   # 1 = keep, 0 = zero

        # Scalar cutoffs → implied stop-bands
        bands = list(self.stop_bands)
        if self.low_cutoff is not None and self.low_cutoff > 0:
            bands.append((0.0, float(self.low_cutoff)))
        if self.high_cutoff is not None and self.high_cutoff < 1.0:
            bands.append((float(self.high_cutoff), 1.0))

        for f_lo, f_hi in bands:
            mask[(f_n >= f_lo) & (f_n <= f_hi)] = 0.0

        Y_filtered = Y * mask
        y_out = np.fft.irfft(Y_filtered, n=n)
        return y_out.astype(float)
