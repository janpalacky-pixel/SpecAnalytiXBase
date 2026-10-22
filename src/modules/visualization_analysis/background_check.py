# src/modules/visualization_analysis/background_check.py
"""Do the spectra still sit on a large shared background? Qt-free.

NMF and MCR-ALS (standalone and in the 2D map) need baseline-corrected
spectra. On raw spectra that sit on a large flat background - e.g. a
detector offset of ~670 counts under bands only ~20 high (the Chlorella
Raman map) - every component has to carry part of that background and
the components split it between them almost arbitrarily, point by point:
the component spectra come out jagged ("a comb") and the maps barely show
real structure, while the lack of fit still looks excellent. The help
pages say so ("Baseline-correct first"); this check lets the program say
it too, at the moment it happens.

The measure, per spectrum: the background level = a low percentile of its
values (2 %), the band height = a high percentile (98 %) minus that level.
Over all spectra the medians are compared: a background larger than the
bands themselves (ratio > 1) is reported. Signed data (CD, a background
around zero) are never reported here - they have their own warning about
negative values.
"""

import numpy as np

LOW, HIGH = 2, 98          # percentiles: robust against single spikes
RATIO = 1.0                # background level / band height above which we warn


def shared_background(spectra):
    """(level, height) - medians over the spectra of the background level
    and of the band height above it; (None, None) when there is nothing."""
    levels, heights = [], []
    for s in spectra:
        y = np.asarray(s.get('y_scale', ()), dtype=float)
        y = y[np.isfinite(y)]
        if y.size < 3:
            continue
        lo, hi = np.percentile(y, [LOW, HIGH])
        levels.append(lo)
        heights.append(hi - lo)
    if not levels:
        return None, None
    return float(np.median(levels)), float(np.median(heights))


def warning_text(spectra, method):
    """The warning for `method` ('NMF' or 'MCR-ALS'), or None when the
    background is not large compared with the bands."""
    level, height = shared_background(spectra)
    if level is None or level <= 0 or height <= 0 or level / height <= RATIO:
        return None
    return (f"The spectra sit on a large background (about {level:.3g}, while their bands are "
            f"only about {height:.3g} high). {method} then spends its components on the "
            f"background and splits it between them, so the component spectra come out jagged "
            f"and the maps or amounts barely show real differences - even when the lack of fit "
            f"looks excellent. Baseline-correct the spectra first (Spectra Processing › "
            f"Automated Baseline), then run {method} again.")
