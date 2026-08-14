# src/modules/data_analysis/resolution_enhancement_manager.py
"""
Spectral resolution enhancement via Wiener deconvolution.

The measured spectrum y_m(x) is modelled as the convolution of the true
spectrum y_t(x) with the instrument response function h(x):

    y_m = y_t * h  (convolution)

Wiener deconvolution recovers y_t in Fourier space:

    Y_t(f) = Y_m(f) * H*(f) / (|H(f)|^2 + 1/SNR)

where:
    Y_m(f)  = FFT of the measured spectrum
    H(f)    = FFT of the IRF (modelled as Gaussian with width sigma)
    H*(f)   = complex conjugate of H(f)
    SNR     = signal-to-noise ratio (regularisation; higher = more aggressive)

The IRF is modelled as a Gaussian:

    h(x) = exp(-x^2 / (2 * sigma^2))

where sigma is the IRF half-width (in x-axis units, e.g. cm^-1).

References
----------
Press et al., Numerical Recipes, Chapter 13 (Wiener filtering)
"""

import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)


class ResolutionEnhancementManager:

    def __init__(self):
        self.irf_sigma  = 2.0    # IRF half-width in x-axis units
        self.snr        = 100.0  # signal-to-noise ratio
        self.method     = 'wiener'  # 'wiener' only for now
        # Labels of any spectra that couldn't be deconvolved on the most
        # recent enhance() call (too few points, degenerate result, etc.)
        # — see that method's docstring.
        self.failed_labels = []

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def enhance(self, spectra: list, irf_sigma: float,
                snr: float, progress_callback=None) -> list:
        """
        Apply Wiener deconvolution to a list of spectrum dicts.

        Parameters
        ----------
        spectra   : list of spectrum dicts with 'x_scale', 'y_scale', 'label'
        irf_sigma : IRF Gaussian half-width in x-axis units (e.g. cm^-1)
        snr       : signal-to-noise ratio (regularisation parameter)
                    Higher SNR → more aggressive sharpening (more noise amplification)
                    Lower SNR  → conservative (smoother result)
        progress_callback : optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before.

        Returns new spectrum dicts (originals not modified). A spectrum
        that can't be deconvolved (too few points, degenerate x-axis,
        etc.) is returned UNCHANGED with a log warning, rather than
        either corrupting it with NaN or letting one bad spectrum abort
        the whole batch — see self.failed_labels.
        """
        self.irf_sigma = irf_sigma
        self.snr       = snr
        self.failed_labels = []
        result = []
        for i, s in enumerate(spectra):
            notify_progress(progress_callback, i)
            x = np.asarray(s['x_scale'], dtype=float)
            y = np.asarray(s['y_scale'], dtype=float)
            try:
                if len(x) < 4 or len(y) < 4:
                    raise ValueError(f"only {len(y)} points (need at least 4)")
                y_enh = self._wiener_deconvolve(x, y, irf_sigma, snr)
                if not np.all(np.isfinite(y_enh)):
                    # Confirmed reachable: a degenerate spectrum (e.g. too
                    # few points, or a near-zero x-step) can produce NaN
                    # from _wiener_deconvolve without ever raising an
                    # exception — numpy's own divide-by-zero/empty-mean
                    # warnings don't stop execution by default, so this
                    # would otherwise have been silently returned as a
                    # "successful" enhancement full of NaN.
                    raise ValueError("deconvolution produced non-finite values")
            except Exception as exc:
                logger.warning(
                    "Resolution enhancement failed for '%s': %s — left unchanged.",
                    s.get('label', '?'), exc
                )
                self.failed_labels.append(s.get('label', '?'))
                # Record the failed attempt too, same reasoning as
                # AutomatedBaselineManager.apply_correction: without this,
                # a failed spectrum silently gets no correction_history
                # entry at all — its own metadata gives no indication
                # this operation was ever even attempted on it, let alone
                # that it failed. self.failed_labels above is still the
                # thing the caller/dialog actually surfaces as a warning;
                # this is the same information, just also recorded on the
                # spectrum's own permanent record.
                failed_spec = dict(s)
                failed_spec['metadata'] = dict(s.get('metadata') or {})
                failed_spec['metadata']['correction_history'] = append_correction_history(
                    s.get('metadata'), 'Resolution enhancement',
                    {'irf_sigma': irf_sigma, 'snr': snr, 'success': False, 'error': str(exc)}
                )
                result.append(failed_spec)
                continue
            new_s = dict(s)
            # dict(s) above is a SHALLOW copy — new_s['metadata'] is still
            # the exact same dict object as s['metadata'] unless replaced
            # with its own copy first (see the shallow-copy metadata bug
            # pattern in 00_SHARED_PROCESS.md).
            new_s['metadata'] = dict(s.get('metadata') or {})
            new_s['y_scale'] = y_enh
            new_s['metadata']['correction_history'] = append_correction_history(
                s.get('metadata'), 'Resolution enhancement',
                {'irf_sigma': irf_sigma, 'snr': snr, 'success': True}
            )
            result.append(new_s)
        logger.info("ResolutionEnhancementManager: enhanced %d/%d spectra "
                    "(sigma=%.2f, SNR=%.1f)", len(spectra) - len(self.failed_labels),
                    len(spectra), irf_sigma, snr)
        return result

    def preview(self, x: np.ndarray, y: np.ndarray,
                irf_sigma: float, snr: float) -> np.ndarray:
        """Return enhanced y for a single spectrum (preview use)."""
        return self._wiener_deconvolve(x, y, irf_sigma, snr)

    # ------------------------------------------------------------------ #
    # Core algorithm                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _wiener_deconvolve(x: np.ndarray, y: np.ndarray,
                            irf_sigma: float, snr: float) -> np.ndarray:
        """
        Wiener deconvolution assuming a Gaussian IRF.

        Works on uniformly-spaced x. If x is not uniform, the result is
        still computed on the x-grid as given (np.gradient handles non-uniform
        spacing, but the IRF is defined in x-units so it still applies).
        """
        n    = len(y)
        dx   = float(np.median(np.diff(x)))  # x-step in x-units
        if dx <= 0:
            dx = 1.0

        # Build Gaussian IRF centred at 0, length n, in x-units
        x_irf  = np.arange(n) * dx
        # Shift so centre is at 0 (circular)
        x_irf  = np.where(x_irf <= n * dx / 2, x_irf, x_irf - n * dx)
        h      = np.exp(-x_irf**2 / (2.0 * irf_sigma**2))
        h     /= h.sum()   # normalise to unit area

        # FFT
        Y = np.fft.rfft(y, n=n)
        H = np.fft.rfft(h, n=n)

        # Wiener filter
        H_conj = np.conj(H)
        H_abs2 = np.abs(H)**2
        W      = H_conj / (H_abs2 + 1.0 / snr)

        Y_enhanced = Y * W
        y_enhanced = np.fft.irfft(Y_enhanced, n=n)

        # Trim/pad to original length
        y_enhanced = y_enhanced[:n]

        # Soft clip: prevent extreme negative artefacts
        # (deconvolution can produce ringing for high SNR)
        y_min = float(y.min()) - float(np.ptp(y)) * 0.2
        y_max = float(y.max()) + float(np.ptp(y)) * 0.2
        y_enhanced = np.clip(y_enhanced, y_min, y_max)

        return y_enhanced
