# src/modules/visualization_analysis/reference_matching_manager.py
"""
Reference Library Matching manager.

Loads a reference library from one or more CSV/text files (same format
as the main spectra importer), computes the x-axis overlap between each
query–reference pair, and scores only on the overlapping region.

Overlap detection
-----------------
For each query–reference pair the overlap fraction is computed as:

    overlap_q   = len(overlap region) / len(query x-range)
    overlap_ref = len(overlap region) / len(reference x-range)
    overlap_pct = min(overlap_q, overlap_ref) * 100

Matches where overlap_pct < min_overlap_pct (default 50 %) are
assigned score = NaN and flagged as unreliable.

Supported metrics
-----------------
cosine      : dot(a, b) / (||a|| * ||b||)   — scale-invariant, default
pearson     : Pearson correlation coefficient
euclidean   : 1 / (1 + ||a - b||)           — bounded to (0, 1]
"""

import numpy as np
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

_MIN_OVERLAP_DEFAULT = 50.0   # percent

# np.trapz was removed in NumPy 2.0 (renamed to np.trapezoid). This shim
# means _normalize's 'unit_area' mode works on either NumPy version
# instead of crashing with AttributeError on 2.0+.
_trapz = getattr(np, 'trapezoid', None) or np.trapz


class ReferenceMatchingManager:

    METRICS = ['cosine', 'pearson', 'euclidean']

    def __init__(self):
        self._library: list = []
        self.library_path = None

    # ------------------------------------------------------------------ #
    # Library loading                                                      #
    # ------------------------------------------------------------------ #

    def load_library(self, file_paths: list,
                     delimiter=None, decimal_separator=None,
                     header=None) -> int:
        """
        Load reference spectra from one or more files.
        Reuses SpectrumManager so all importer formats are supported.
        Returns the number of reference spectra loaded.
        """
        from src.modules.core.spectrum_manager import SpectrumManager
        mgr = SpectrumManager()
        errors = []
        for path in file_paths:
            try:
                mgr.load_spectrum_from_file(
                    path,
                    delimiter=delimiter,
                    decimal_separator=decimal_separator,
                    header=header,
                )
            except Exception as exc:
                errors.append((path, str(exc)))
                logger.warning("Reference library load failed for '%s': %s", path, exc)

        self._library = [
            {
                'label': label,
                'x':     np.asarray(sp.x_scale, dtype=float),
                'y':     np.asarray(sp.y_scale, dtype=float),
            }
            for label, sp in mgr.spectra.items()
        ]
        self.library_path = file_paths
        logger.info("Reference library: %d spectra loaded", len(self._library))
        if errors:
            raise ValueError(
                f"Failed to load {len(errors)} file(s):\n" +
                "\n".join(f"  {p}: {e}" for p, e in errors)
            )
        return len(self._library)

    @property
    def library_size(self) -> int:
        return len(self._library)

    # ------------------------------------------------------------------ #
    # Matching                                                             #
    # ------------------------------------------------------------------ #

    def match(self, spectra: list, settings: dict) -> list:
        """
        Compute similarity scores between each query spectrum and all
        library references, restricted to the overlapping x-region.

        Parameters
        ----------
        spectra  : list of spectrum dicts (query spectra)
        settings : dict with keys
            metric          : 'cosine' | 'pearson' | 'euclidean'
            top_n           : int
            normalization   : 'none' | 'vector' | 'max_peak' | 'unit_area'
            min_overlap_pct : float  — minimum overlap % (default 50)

        Returns
        -------
        list of result dicts, one per query spectrum:
            label   : str
            matches : list of {ref_label, score, overlap_pct,
                               reliable, x_overlap, y_q_overlap,
                               y_ref_overlap}
                      sorted best-first (NaN scores last)

        A library entry carrying a 'source_key' that matches the query's
        own identity key is skipped entirely (see _key_for) — this is how
        "From loaded spectra" mode avoids matching a spectrum against
        itself when the same spectrum is selected as both a query and a
        reference. File-loaded library entries never carry a 'source_key',
        so they can never be excluded this way even if a file entry
        happens to share a query's label by coincidence — exclusion is by
        actual identity, never by label text.
        """
        if not self._library:
            return []

        metric          = settings.get('metric', 'cosine')
        top_n           = int(settings.get('top_n', 5))
        normalization   = settings.get('normalization', 'none')
        min_overlap_pct = float(settings.get('min_overlap_pct', _MIN_OVERLAP_DEFAULT))

        results = []
        for s in spectra:
            x_q = np.asarray(s.get('x_scale', []), dtype=float)
            y_q = np.asarray(s.get('y_scale', []), dtype=float)
            if len(x_q) < 2:
                continue

            query_key = self._key_for(s)

            scores = []
            for ref in self._library:
                if ref.get('source_key') is not None and ref['source_key'] == query_key:
                    continue  # comparing a spectrum against itself — not a match

                overlap_pct, x_ov, y_q_ov, y_ref_ov = self._compute_overlap(
                    x_q, y_q, ref['x'], ref['y']
                )
                reliable = overlap_pct >= min_overlap_pct

                if reliable and len(x_ov) >= 2:
                    y_q_n   = self._normalize(x_ov, y_q_ov, normalization)
                    y_ref_n = self._normalize(x_ov, y_ref_ov, normalization)
                    score   = self._score(y_q_n, y_ref_n, metric)
                else:
                    score = float('nan')

                scores.append({
                    'ref_label':    ref['label'],
                    'score':        score,
                    'overlap_pct':  overlap_pct,
                    'reliable':     reliable,
                    # Always the genuine overlap region — never fabricated
                    # data outside it. These used to be nulled to None
                    # whenever a match was unreliable, and a SEPARATE,
                    # always-populated 'y_ref_interp' field (flat-
                    # extrapolated across the query's ENTIRE x-range, real
                    # overlap or not) was what the dialog's preview plot
                    # actually drew. That meant a reference with ~0% real
                    # overlap — exactly the "Raman vs CD" case this app's
                    # own help text says overlap detection protects
                    # against — still rendered as a smooth, confident-
                    # looking dashed line spanning the whole plot, over 99%
                    # of it invented. Scoring already correctly refused to
                    # use it (score = NaN above); now the preview can't
                    # draw it either, because the fabricated data doesn't
                    # exist anywhere in this result.
                    'x_overlap':    x_ov,
                    'y_q_overlap':  y_q_ov,
                    'y_ref_overlap': y_ref_ov,
                })

            # Sort: reliable matches first (by score desc), then unreliable
            reliable_scores = [d for d in scores if d['reliable']]
            unreliable      = [d for d in scores if not d['reliable']]
            reliable_scores.sort(key=lambda d: d['score'], reverse=True)
            sorted_scores   = reliable_scores + unreliable

            results.append({
                'label':   s['label'],
                'matches': sorted_scores[:top_n],
            })

        return results

    @staticmethod
    def _key_for(spectrum):
        """Stable per-spectrum identity key — unique_id if present,
        otherwise label. Used only to detect "is this reference actually
        the same spectrum as this query" (see match()); never used to
        decide whether two spectra are otherwise related, since two
        genuinely different spectra can share a label (see the rest of
        this codebase's _key_for convention)."""
        metadata = spectrum.get('metadata') or {}
        return metadata.get('unique_id') or spectrum.get('label')

    # ------------------------------------------------------------------ #
    # Overlap computation                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_overlap(x_q, y_q, x_ref, y_ref):
        """
        Return (overlap_pct, x_overlap, y_q_on_overlap, y_ref_on_overlap).

        Handles both ascending and descending x-axes by sorting to ascending
        before any comparison or interpolation (np.interp requires ascending xp).
        """
        # Ensure both arrays are sorted ascending
        if len(x_q) > 1 and x_q[0] > x_q[-1]:
            x_q, y_q = x_q[::-1], y_q[::-1]
        if len(x_ref) > 1 and x_ref[0] > x_ref[-1]:
            x_ref, y_ref = x_ref[::-1], y_ref[::-1]

        q_lo, q_hi     = float(x_q.min()),   float(x_q.max())
        ref_lo, ref_hi = float(x_ref.min()), float(x_ref.max())

        ov_lo = max(q_lo, ref_lo)
        ov_hi = min(q_hi, ref_hi)

        if ov_lo >= ov_hi:
            return 0.0, np.array([]), np.array([]), np.array([])

        # Overlap fraction relative to each spectrum's range
        ov_span  = ov_hi - ov_lo
        q_span   = q_hi  - q_lo   if q_hi   > q_lo   else 1.0
        ref_span = ref_hi - ref_lo if ref_hi > ref_lo else 1.0
        overlap_pct = min(ov_span / q_span, ov_span / ref_span) * 100.0

        # Extract query points in the overlap region
        mask   = (x_q >= ov_lo) & (x_q <= ov_hi)
        x_ov   = x_q[mask]
        y_q_ov = y_q[mask]

        if len(x_ov) < 2:
            return overlap_pct, np.array([]), np.array([]), np.array([])

        # Interpolate reference onto the overlap query grid (x_ref is now ascending)
        y_ref_ov = np.interp(x_ov, x_ref, y_ref)

        return overlap_pct, x_ov, y_q_ov, y_ref_ov

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(x, y, method):
        y = y.copy()
        # Accept both internal names and display names
        m = method.replace(' ', '_')
        if m == 'vector':
            norm = np.linalg.norm(y)
            return y / norm if norm > 1e-12 else y
        elif m == 'max_peak':
            peak = np.max(np.abs(y))
            return y / peak if peak > 1e-12 else y
        elif m == 'unit_area':
            area = _trapz(np.abs(y), x)
            return y / area if area > 1e-12 else y
        return y

    @staticmethod
    def _score(a, b, metric):
        if metric == 'cosine':
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na < 1e-12 or nb < 1e-12:
                return 0.0
            return float(np.dot(a, b) / (na * nb))
        elif metric == 'pearson':
            if np.std(a) < 1e-12 or np.std(b) < 1e-12:
                return 0.0
            return float(np.corrcoef(a, b)[0, 1])
        elif metric == 'euclidean':
            # Use RMS (root mean square) distance so score is independent
            # of spectrum length and absolute intensity scale
            rms = float(np.sqrt(np.mean((a - b)**2)))
            # Normalise by mean intensity to make it relative
            mean_int = float(np.mean(np.abs(a) + np.abs(b))) / 2.0
            if mean_int > 1e-12:
                rms_rel = rms / mean_int
            else:
                rms_rel = rms
            return float(1.0 / (1.0 + rms_rel))
        return 0.0
