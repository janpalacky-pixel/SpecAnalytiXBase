# src/modules/data_analysis/snip_baseline_manager.py
"""
SNIP (Statistics-sensitive Non-linear Iterative Peak-clipping) baseline
correction manager.

Algorithm reference
-------------------
Ryan, C.G., Clayton, E., Griffin, W.L., Sie, S.H., Cousens, D.R. (1988).
"SNIP, a statistics-sensitive background treatment for the quantitative
analysis of PIXE spectra in geoscience applications."
Nuclear Instruments and Methods in Physics Research B, 34(3), 396–402.

The implementation follows the standard spectroscopic formulation:
    1. Transform:  y' = sqrt(y + 3/8)   (variance-stabilising, optional)
    2. For m = 1 … n_iter:
         y'[i] = min(y'[i],  (y'[i-m] + y'[i+m]) / 2)
    3. Back-transform: y_baseline = (y')² - 3/8
    4. baseline = clip(y_baseline, 0, original_max)   (optional smoothing)

The decreasing-window variant uses m = n_iter … 1, which is slightly more
conservative and preferred for smooth baselines.
"""

import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.progress_utils import notify_progress

logger = get_logger(__name__)


class SNIPBaselineManager:
    """Applies SNIP baseline correction to a list of spectrum dicts."""

    def __init__(self):
        self.n_iter           = 100     # number of clipping iterations
        self.decreasing       = True    # use decreasing window order
        self.smooth_window    = 0       # optional pre-smoothing half-window (0 = off)
        self.transform        = True    # apply sqrt variance-stabilising transform
        # Labels of any spectra skipped on the most recent apply_correction()
        # call (too few points for SNIP to run at all) — see that method.
        self.skipped_labels   = []

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update_settings(self, settings: dict):
        self.n_iter        = int(settings.get('n_iter',        self.n_iter))
        self.decreasing    = bool(settings.get('decreasing',   self.decreasing))
        self.smooth_window = int(settings.get('smooth_window', self.smooth_window))
        self.transform     = bool(settings.get('transform',    self.transform))

    def apply_correction(self, spectra: list, settings: dict, progress_callback=None) -> list:
        """
        Subtract the SNIP baseline from each spectrum.

        Parameters
        ----------
        spectra  : list of spectrum dicts
        settings : dict with keys n_iter, decreasing, smooth_window, transform
        progress_callback : optional callable, invoked every 50 spectra
            during the loop below. Same hook/contract as
            plotting.py's overlay_plot_mode — a caller showing a progress
            dialog can pass e.g. `lambda: QApplication.processEvents()`
            here so the dialog's busy animation actually animates during
            a large batch, instead of the Qt event loop being frozen for
            this whole call. None (the default) — no change from before.

        Returns
        -------
        list of new spectrum dicts (originals not modified)
        """
        self.update_settings(settings)
        processed = []
        self.skipped_labels = []
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            new_spec = dict(spectrum)
            # dict(spectrum) above is a SHALLOW copy — new_spec['metadata']
            # is still the exact same dict object as spectrum['metadata']
            # unless replaced with its own copy first (see the
            # shallow-copy metadata bug pattern in 00_SHARED_PROCESS.md).
            new_spec['metadata'] = dict(spectrum.get('metadata') or {})
            y = np.asarray(spectrum.get('y_scale', []), dtype=float)
            if len(y) < 3:
                self.skipped_labels.append(spectrum.get('label', '?'))
                logger.warning(
                    "SNIP baseline: '%s' has fewer than 3 data points — "
                    "skipping, spectrum left unchanged.",
                    spectrum.get('label', '?')
                )
                new_spec['metadata']['correction_history'] = append_correction_history(
                    spectrum.get('metadata'), 'SNIP Baseline',
                    {'skipped': True, 'n_iter': self.n_iter, 'decreasing': self.decreasing,
                     'smooth_window': self.smooth_window, 'transform': self.transform}
                )
                processed.append(new_spec)
                continue
            baseline = self._compute_baseline(y)
            new_spec['y_scale'] = y - baseline
            new_spec['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'SNIP Baseline',
                {'skipped': False, 'n_iter': self.n_iter, 'decreasing': self.decreasing,
                 'smooth_window': self.smooth_window, 'transform': self.transform}
            )
            processed.append(new_spec)
            logger.debug("SNIP baseline subtracted from '%s'", spectrum.get('label', '?'))
        return processed

    def compute_baseline(self, y: np.ndarray, settings: dict) -> np.ndarray:
        """
        Return the baseline array (without subtracting it).
        Used by the dialog for live preview.
        """
        self.update_settings(settings)
        return self._compute_baseline(np.asarray(y, dtype=float))

    # ------------------------------------------------------------------ #
    # Core algorithm                                                       #
    # ------------------------------------------------------------------ #

    def _compute_baseline(self, y: np.ndarray) -> np.ndarray:
        n = len(y)

        # Optional pre-smoothing (moving average)
        if self.smooth_window > 0:
            w  = self.smooth_window
            y  = np.convolve(y, np.ones(2 * w + 1) / (2 * w + 1), mode='same')

        # Variance-stabilising transform: sqrt(y + 3/8)
        if self.transform:
            # Shift so minimum is >= 0 before taking sqrt
            y_shifted = y - y.min()
            z = np.sqrt(y_shifted + 3.0 / 8.0)
        else:
            z = y.copy()

        # Iterative clipping
        window_range = (range(self.n_iter, 0, -1)
                        if self.decreasing
                        else range(1, self.n_iter + 1))
        for m in window_range:
            # Only update interior points; leave edges untouched
            lo = m
            hi = n - m
            if lo >= hi:
                break
            left  = z[lo - m : hi - m]
            right = z[lo + m : hi + m]
            mid   = z[lo:hi]
            z[lo:hi] = np.minimum(mid, (left + right) / 2.0)

        # Back-transform
        if self.transform:
            baseline_shifted = z ** 2 - 3.0 / 8.0
            # Re-add the shift that was removed before the transform
            baseline = baseline_shifted + y.min()
        else:
            baseline = z

        # Clip so baseline never exceeds original signal
        baseline = np.clip(baseline, None, y)
        return baseline
