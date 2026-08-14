# src/modules/data_analysis/spike_removal_manager.py

import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.correction_history import append_correction_history

logger = get_logger(__name__)


class SpikeRemovalManager:
    """
    Manages spike detection and removal from spectra.

    Two modes
    ---------
    Automatic
        Detects spikes using a modified Z-score on the second derivative,
        then replaces each spike with linear interpolation from neighbouring
        clean points.  The second derivative amplifies narrow spikes (which
        span only 1-3 points) while leaving broad spectral features almost
        unchanged.

    Interactive / Manual
        Exposes the detected spike positions so the user can accept, reject
        or add them manually before committing the removal.

    Algorithm reference
    -------------------
    Whitaker & Hayes (2018) "A simple algorithm for despiking Raman spectra",
    Chemometrics and Intelligent Laboratory Systems 179, 82-84.
    Modified Z-score on the second derivative:
        d²y = y[i+1] - 2*y[i] + y[i-1]
        M   = median(d²y)
        MAD = median(|d²y - M|)
        Zi  = 0.6745 * (d²y[i] - M) / MAD
    A point i is a spike if |Zi| > threshold.
    """

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    def __init__(self):
        self.threshold     = 7.0    # default modified Z-score threshold
        self.half_window   = 2      # half-width of the spike window to replace
        self.auto_detected = {}     # {key: [spike_indices]}  auto hits per spectrum
        self.manual_extra  = {}     # {key: [spike_indices]}  user-added points
        self.rejected      = {}     # {key: {spike_index}}    user-rejected auto hits

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum key — uses the spectrum's persistent
        unique_id rather than its label. Labels are not stable
        identifiers: renaming a spectrum doesn't change its identity, and
        two unrelated spectra (e.g. from separate import sessions, or a
        re-imported file producing the same filename-derived label) can end
        up sharing a label even though they've never had anything to do
        with each other. Falls back to label only if a spectrum genuinely
        has no unique_id, which shouldn't normally happen.

        IMPORTANT — scope of use: this is ONLY for the long-lived manager
        instance owned by SpikeRemovalController, at the boundary where its
        auto_detected / manual_extra / rejected dicts are read into, or
        written back from, the interactive dialog (see
        SpikeRemovalController.show_interactive_dialog). The dialog itself
        creates its OWN short-lived SpikeRemovalManager instance and is
        modal (no rename can happen while it's open), so it consistently
        uses spectrum['label'] as the key everywhere internally — and this
        class's own methods (detect_spikes, _remove_from_spectra, etc.)
        must keep matching that, since the dialog calls them directly on
        its own instance. Do NOT switch those methods to use _key_for
        internally — doing so previously broke auto-detection entirely,
        because detection started writing under the unique_id while every
        other lookup in the dialog still read by label.
        """
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum['label']

    def prune_to_current_spectra(self, current_spectra):
        """Remove per-spectrum entries (auto/manual/rejected) for any key
        not belonging to a spectrum in current_spectra. Without this, a
        spectrum that's gone (cleared, replaced by a new import) leaves its
        old spike markings behind forever, keyed by whatever identified it
        at the time — and if a later import happens to reuse that same
        label, it would silently inherit them."""
        current_keys = {self._key_for(s) for s in current_spectra}
        for d in (self.auto_detected, self.manual_extra, self.rejected):
            for key in list(d.keys()):
                if key not in current_keys:
                    del d[key]

    # ------------------------------------------------------------------ #
    # Public API — automatic detection                                    #
    # ------------------------------------------------------------------ #

    def detect_spikes(self, spectra, threshold=None, half_window=None):
        """
        Run automatic spike detection on a list of spectra.

        Parameters
        ----------
        spectra      : list of spectrum dicts (must have 'y_scale' and 'label')
        threshold    : modified Z-score threshold (default: self.threshold)
        half_window  : half-width of the replacement window (default: self.half_window)

        Returns
        -------
        dict  {label: list_of_spike_indices}
        """
        if threshold   is not None: self.threshold   = threshold
        if half_window is not None: self.half_window = half_window

        self.auto_detected = {}
        for spectrum in spectra:
            label = spectrum['label']
            y     = np.asarray(spectrum['y_scale'], dtype=float)
            self.auto_detected[label] = self._find_spike_indices(y)

        logger.debug(
            "Spike detection: threshold=%.1f, half_window=%d, spectra=%d",
            self.threshold, self.half_window, len(spectra)
        )
        return dict(self.auto_detected)

    def apply_automatic_removal(self, spectra, threshold=None, half_window=None):
        """
        Detect and immediately remove spikes.  Returns a new list of spectra
        with spikes replaced by linear interpolation.

        Parameters
        ----------
        spectra      : list of spectrum dicts
        threshold    : modified Z-score threshold
        half_window  : half-width of the replacement window

        Returns
        -------
        list of processed spectrum dicts (deep copies — originals untouched)
        """
        self.detect_spikes(spectra, threshold, half_window)
        return self._remove_from_spectra(spectra, self.auto_detected)

    # ------------------------------------------------------------------ #
    # Public API — interactive / manual                                   #
    # ------------------------------------------------------------------ #

    def get_effective_spikes(self, key):
        """
        Return the effective spike list for a spectrum, combining auto
        detections (minus rejected ones) with any manually added points.

        Args:
            key (str): Per-spectrum key — see _key_for().
        """
        auto  = set(self.auto_detected.get(key, []))
        bad   = self.rejected.get(key, set())
        extra = set(self.manual_extra.get(key, []))
        return sorted((auto - bad) | extra)

    def reject_spike(self, key, index):
        """Mark an auto-detected spike as rejected (user decided it is not a spike)."""
        self.rejected.setdefault(key, set()).add(index)

    def accept_spike(self, key, index):
        """Undo a previous rejection."""
        self.rejected.get(key, set()).discard(index)

    def add_manual_spike(self, key, index):
        """Add a point manually selected by the user."""
        lst = self.manual_extra.setdefault(key, [])
        if index not in lst:
            lst.append(index)
            lst.sort()

    def remove_manual_spike(self, key, index):
        """Remove a manually added point."""
        lst = self.manual_extra.get(key, [])
        if index in lst:
            lst.remove(index)

    def apply_interactive_removal(self, spectra):
        """
        Remove spikes using the effective spike lists (auto − rejected + manual).
        Returns a new list of processed spectra.
        """
        effective = {
            spectrum['label']: self.get_effective_spikes(spectrum['label'])
            for spectrum in spectra
        }
        return self._remove_from_spectra(spectra, effective)

    def reset_for_spectrum(self, key):
        """Reset all detection/override state for a single spectrum."""
        self.auto_detected.pop(key, None)
        self.manual_extra.pop(key, None)
        self.rejected.pop(key, None)

    def reset_all(self):
        """Reset all state."""
        self.auto_detected = {}
        self.manual_extra  = {}
        self.rejected      = {}

    # ------------------------------------------------------------------ #
    # Spike detection algorithm                                            #
    # ------------------------------------------------------------------ #

    def _find_spike_indices(self, y):
        """
        Return indices of spike peaks using the modified Z-score of the
        2nd derivative (Whitaker & Hayes 2018).

        After finding candidate indices from the d2 score, each candidate
        is snapped to the local |y| maximum within ±half_window so that
        the marker lands on the actual spike tip rather than on the steep
        edge one point away.
        """
        if len(y) < 4:
            return []

        # Second derivative (length n-2); d2[i] corresponds to original index i+1
        d2  = np.diff(y, n=2)
        M   = np.median(d2)
        MAD = np.median(np.abs(d2 - M))

        if MAD < 1e-12:
            return []   # flat spectrum — nothing to detect

        Zi = 0.6745 * (d2 - M) / MAD
        hit_d2   = np.where(np.abs(Zi) > self.threshold)[0]
        hit_orig = (hit_d2 + 1).tolist()   # shift back to original indices

        # Snap each candidate to the local |y| maximum within ±half_window.
        # This corrects the systematic off-by-one caused by the d2 peak
        # falling on the descending edge of a sharp spike rather than at
        # the tip.
        n = len(y)
        snapped = []
        for idx in hit_orig:
            lo   = max(0, idx - self.half_window)
            hi   = min(n - 1, idx + self.half_window)
            peak = int(lo + np.argmax(np.abs(y[lo:hi + 1] - np.median(y))))
            snapped.append(peak)

        # Merge candidates whose snapped positions are within half_window of
        # each other — keep the one with the largest |y| deviation.
        if not snapped:
            return []

        snapped_arr = np.array(sorted(set(snapped)))
        merged = []
        group  = [snapped_arr[0]]
        for idx in snapped_arr[1:]:
            if idx - group[-1] <= self.half_window:
                group.append(idx)
            else:
                # Keep the peak with max |y - median(y)| in this group
                med = np.median(y)
                best = int(group[np.argmax([abs(y[g] - med) for g in group])])
                merged.append(best)
                group = [idx]
        med  = np.median(y)
        best = int(group[np.argmax([abs(y[g] - med) for g in group])])
        merged.append(best)
        return merged

    # ------------------------------------------------------------------ #
    # Spike replacement                                                    #
    # ------------------------------------------------------------------ #

    def _remove_from_spectra(self, spectra, spike_map):
        """
        Replace detected spikes with linear interpolation.

        spike_map : {label: [spike_indices]}
        Returns a list of new spectrum dicts (originals not modified).

        Metadata: only spectra that actually had ≥1 spike removed get a
        correction_history entry — a spectrum with nothing to remove
        wasn't corrected, same "affected spectra only" convention
        CosmicRayManager.apply() uses. Records BOTH the raw pixel index
        (1-based, matching CosmicRayManager's convention) and the x-scale
        value at each removed spike, since the index alone only makes
        sense if you also know the axis — this used to record only the
        raw 0-based index, unlike Cosmic Ray Removal's equivalent record.
        """
        processed = []
        for spectrum in spectra:
            label   = spectrum['label']
            indices = spike_map.get(label, [])
            new_y   = self._interpolate_spikes(
                np.asarray(spectrum['y_scale'], dtype=float),
                indices,
                self.half_window
            )
            new_spec = dict(spectrum)
            # dict(spectrum) above is a SHALLOW copy — new_spec['metadata']
            # is still the exact same dict object as spectrum['metadata']
            # unless replaced with its own copy first (see the
            # shallow-copy metadata bug pattern in 00_SHARED_PROCESS.md).
            new_spec['metadata'] = dict(spectrum.get('metadata') or {})
            new_spec['y_scale'] = new_y
            if indices:
                x_scale = np.asarray(spectrum['x_scale'], dtype=float)
                sorted_indices = sorted(indices)
                new_spec['metadata']['correction_history'] = append_correction_history(
                    spectrum.get('metadata'), 'Spike removal',
                    {
                        'spike_count': len(indices),
                        'half_window': self.half_window,
                        'spike_x_positions': [round(float(x_scale[idx]), 4) for idx in sorted_indices],
                        'spike_x_indices': [int(idx) + 1 for idx in sorted_indices],
                    }
                )
            processed.append(new_spec)
            logger.debug(
                "Removed %d spikes from '%s'", len(indices), label
            )
        return processed

    @staticmethod
    def _interpolate_spikes(y, spike_indices, half_window):
        """
        Replace each spike region with linear interpolation between the
        nearest clean neighbours.
        """
        if not spike_indices:
            return y.copy()

        y_out = y.copy()
        n     = len(y_out)

        # Build a set of all indices that belong to any spike window
        spike_pixels = set()
        for center in spike_indices:
            lo = max(0, center - half_window)
            hi = min(n - 1, center + half_window)
            for px in range(lo, hi + 1):
                spike_pixels.add(px)

        # Interpolate each pixel in the spike region
        for px in sorted(spike_pixels):
            # Find nearest clean left neighbour
            lo = px - 1
            while lo >= 0 and lo in spike_pixels:
                lo -= 1
            # Find nearest clean right neighbour
            hi = px + 1
            while hi < n and hi in spike_pixels:
                hi += 1

            if lo < 0 and hi >= n:
                # Entire spectrum is flagged — cannot interpolate
                pass
            elif lo < 0:
                y_out[px] = y_out[hi]
            elif hi >= n:
                y_out[px] = y_out[lo]
            else:
                # Linear interpolation
                t = (px - lo) / (hi - lo)
                y_out[px] = y_out[lo] * (1 - t) + y_out[hi] * t

        return y_out

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #

    def get_summary(self, spectra):
        """
        Return a summary dict for logging / display.

        Returns
        -------
        {
          'total_spectra': int,
          'spectra_with_spikes': int,
          'total_spikes': int,
          'details': {label: n_spikes}
        }
        """
        details = {}
        for spectrum in spectra:
            label = spectrum['label']
            n = len(self.get_effective_spikes(label))
            details[label] = n

        return {
            'total_spectra':      len(spectra),
            'spectra_with_spikes': sum(1 for n in details.values() if n > 0),
            'total_spikes':        sum(details.values()),
            'details':             details,
        }
