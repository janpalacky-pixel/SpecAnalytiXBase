# src/modules/visualization_analysis/qc_outlier_manager.py

import numpy as np
from scipy import stats

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


class QCOutlierManager:
    """Business logic for PCA-based outlier / QC flagging across a batch
    of spectra sharing one common x-axis.

    Two complementary, classic chemometric diagnostics (Jackson, 1991;
    MacGregor & Kourti, 1995 -- the standard "distance-distance" approach
    used throughout multivariate statistical process control):

        Hotelling's T^2  -- how far a spectrum's PCA scores are from the
            bulk of the batch, WITHIN the model (an unusual but still
            model-shaped combination of the variation the model already
            captures -- e.g. an atypical concentration/mixture, an
            unusually strong or weak version of a real, expected pattern).

        Q-residual (SPE, squared prediction error) -- how much of a
        spectrum's shape the model does NOT explain at all (variation
        OUTSIDE the model -- e.g. a spike, a baseline artifact, a
        contaminated or mislabeled sample, anything that doesn't look
        like the rest of the batch in the first place).

    A spectrum can be flagged on either, both, or neither -- the two are
    independent and answer different questions ("is this an unusual but
    plausible member of the batch?" vs "does this even belong to the
    batch's spectral family at all?").

    Control limits:
        T^2 limit -- exact F-distribution formula (Jackson, 1991):
            T2_lim = k(n-1)/(n-k) * F_alpha(k, n-k)
        Q limit -- Jackson-Mudholkar (1979) approximation from the
            eigenvalues of the DISCARDED components.

    Pure computation, no Qt -- safe to call from a background QThread.
    """

    def __init__(self):
        self.labels = None
        self.x_axis = None
        self.mean_spectrum = None
        self.n_components = None
        self.n_spectra = None
        self.explained_variance = None   # percent, per retained component
        self.scores = None               # (n_spectra x n_components)
        self.loadings = None             # (n_components x n_wl)
        self.t2 = None                   # (n_spectra,)
        self.q = None                    # (n_spectra,)
        self.t2_limit = None
        self.q_limit = None
        self.t2_flag = None              # bool array
        self.q_flag = None               # bool array
        self.residuals = None            # (n_spectra x n_wl), Xc - reconstruction
        self.alpha = None
        self.last_error = None

    def reset(self):
        """Clear all previous results -- same convention as every other
        manager in this codebase (e.g. PcaScoresManager.reset()): without
        this, results from a previous, unrelated spectra selection could
        still be read before a fresh computation finishes."""
        self.__init__()

    # ------------------------------------------------------------------ #
    # Data matrix                                                          #
    # ------------------------------------------------------------------ #

    def build_data_matrix(self, spectra):
        """Build X[n_spectra, n_wl] from spectra that all already share
        one common x-axis (validate this with
        spectra_validation.validate_common_x_axis BEFORE calling this --
        not re-checked here). Returns (x_axis, X, labels)."""
        x_axis = np.asarray(spectra[0]['x_scale'], dtype=float)
        X = np.empty((len(spectra), len(x_axis)), dtype=float)
        labels = []
        for row, spec in enumerate(spectra):
            X[row, :] = np.asarray(spec['y_scale'], dtype=float)
            labels.append(spec.get('label', f'Spectrum {row + 1}'))
        return x_axis, X, labels

    # ------------------------------------------------------------------ #
    # Component-count auto-selection                                      #
    # ------------------------------------------------------------------ #

    def auto_select_n_components(self, explained_variance_ratio, threshold=0.95, max_components=None):
        """Smallest k whose cumulative explained variance reaches
        `threshold` (default 95%) -- the standard, simplest "enough of
        the real signal, not just noise" rule of thumb for a PCA-based
        QC model. Always returns at least 1."""
        cum = np.cumsum(explained_variance_ratio) / 100.0
        k = int(np.searchsorted(cum, threshold) + 1)
        k = max(1, k)
        if max_components is not None:
            k = min(k, max_components)
        return k

    # ------------------------------------------------------------------ #
    # Main computation                                                     #
    # ------------------------------------------------------------------ #

    def compute(self, spectra, n_components=None, variance_threshold=0.95, alpha=0.05):
        """Fit a PCA model to the batch and compute Hotelling T^2 and
        Q-residual (with control limits) for every spectrum.

        Args:
            spectra: list of spectrum dicts, already validated to share
                one common x-axis.
            n_components: number of PCA components to retain for the
                model. If None, auto-selected via
                auto_select_n_components(variance_threshold).
            variance_threshold: cumulative explained-variance fraction
                used for auto-selection (ignored if n_components given).
            alpha: significance level for both control limits (default
                0.05 -> 95% confidence).

        Returns True on success (results available on self.*), False on
        failure (see self.last_error).
        """
        self.last_error = None
        n = len(spectra)

        if n < 5:
            self.last_error = ("Need at least 5 spectra for meaningful PCA-based "
                                "outlier detection (fewer than that, there isn't "
                                "enough of a 'batch' for anything to look unusual "
                                "against).")
            return False

        try:
            x_axis, X, labels = self.build_data_matrix(spectra)
            mean_spectrum = X.mean(axis=0)
            Xc = X - mean_spectrum

            # Full SVD (mean-centered) -- rank is at most min(n-1, n_wl);
            # keeping the full decomposition (not just the retained k) is
            # what lets the Q-residual control limit use the DISCARDED
            # components' eigenvalues (Jackson-Mudholkar), not just an
            # arbitrary noise-floor guess.
            U, s, Vt = np.linalg.svd(Xc, full_matrices=False)
            r = len(s)
            if r < 2:
                self.last_error = "Not enough independent variation across these spectra to fit a PCA model."
                return False

            eigen_all = (s ** 2) / max(n - 1, 1)          # population variance per PC
            total_var = np.sum(eigen_all)
            explained_ratio_all = (eigen_all / total_var * 100.0) if total_var > 0 else np.zeros(r)

            # Reserve at least 1 component for the residual space, and
            # keep k < n so the T^2 F-distribution limit stays computable.
            max_k = max(1, min(r - 1, n - 2))
            if n_components is None:
                k = self.auto_select_n_components(explained_ratio_all, variance_threshold, max_components=max_k)
            else:
                k = max(1, min(int(n_components), max_k))

            scores = U[:, :k] * s[:k]                     # (n x k)
            loadings = Vt[:k, :]                          # (k x n_wl)
            eigen_k = eigen_all[:k]

            # Hotelling T^2: sum over retained components of (score^2 / eigenvalue).
            with np.errstate(divide='ignore', invalid='ignore'):
                t2 = np.sum((scores ** 2) / eigen_k[None, :], axis=1)
            t2 = np.nan_to_num(t2, nan=0.0, posinf=0.0)

            # Q-residual (SPE): leftover after reconstructing from k components.
            X_hat = scores @ loadings
            residuals = Xc - X_hat
            q = np.sum(residuals ** 2, axis=1)

            # --- T^2 control limit (exact F-distribution formula) ---
            t2_limit = None
            if n > k:
                f_val = stats.f.ppf(1 - alpha, k, n - k)
                t2_limit = k * (n - 1) / (n - k) * f_val

            # --- Q control limit (Jackson-Mudholkar approximation) ---
            residual_eigen = eigen_all[k:]
            q_limit = self._jackson_mudholkar_limit(residual_eigen, alpha)

            self.labels = labels
            self.x_axis = x_axis
            self.mean_spectrum = mean_spectrum
            self.n_components = k
            self.n_spectra = n
            self.explained_variance = explained_ratio_all[:k]
            self.scores = scores
            self.loadings = loadings
            self.t2 = t2
            self.q = q
            self.t2_limit = t2_limit
            self.q_limit = q_limit
            self.t2_flag = (t2 > t2_limit) if t2_limit is not None else np.zeros(n, dtype=bool)
            self.q_flag = (q > q_limit) if (q_limit is not None and q_limit > 0) else np.zeros(n, dtype=bool)
            self.residuals = residuals
            self.alpha = alpha
            return True

        except Exception as e:
            logger.error(f"ERROR: QC/outlier computation failed: {e}")
            logger.exception("Traceback:")
            self.last_error = f"QC/outlier computation failed: {e}"
            return False

    @staticmethod
    def _jackson_mudholkar_limit(residual_eigen, alpha):
        """Q (SPE) control limit from the eigenvalues of the DISCARDED
        PCA components (Jackson & Mudholkar, 1979) -- the standard
        approximation used throughout multivariate SPC, avoiding the
        need to assume Q is chi-squared or normally distributed (it
        generally isn't).

        Returns None if there's no residual space at all (k spans every
        available component -- Q is then ~0 for every spectrum and no
        Q-based flagging is possible), or 0.0 if the residual space
        carries no variance.
        """
        theta1 = float(np.sum(residual_eigen))
        if len(residual_eigen) == 0:
            return None
        if theta1 <= 0:
            return 0.0

        theta2 = float(np.sum(residual_eigen ** 2))
        theta3 = float(np.sum(residual_eigen ** 3))

        if theta2 <= 0:
            h0 = 1.0
        else:
            h0 = 1.0 - (2.0 * theta1 * theta3) / (3.0 * theta2 ** 2)
        h0 = max(h0, 1e-6)   # guard against a degenerate (near-zero/negative) h0

        c_alpha = stats.norm.ppf(1 - alpha)
        inner = (c_alpha * np.sqrt(2.0 * theta2 * h0 ** 2) / theta1
                 + 1.0
                 + theta2 * h0 * (h0 - 1.0) / theta1 ** 2)
        if inner <= 0:
            # Degenerate case (can happen with very few discarded
            # components) -- fall back to theta1 itself as a conservative
            # limit rather than raising on a fractional power of a
            # negative base.
            return theta1
        return theta1 * (inner ** (1.0 / h0))

    # ------------------------------------------------------------------ #
    # Per-spectrum diagnostics (for the dialog's plots)                   #
    # ------------------------------------------------------------------ #

    def reconstruction(self, index):
        """Reconstructed (model) spectrum and residual for spectrum
        `index`, in original (non-centered) units -- used by the
        'Residual spectrum' view to show exactly what a flagged spectrum
        doesn't fit."""
        if self.scores is None:
            return None
        recon = self.mean_spectrum + self.scores[index, :] @ self.loadings
        residual = self.residuals[index, :]
        return recon, residual

    def flag_reason(self, index):
        """Short human-readable reason string for spectrum `index`."""
        t2_bad = bool(self.t2_flag[index]) if self.t2_flag is not None else False
        q_bad = bool(self.q_flag[index]) if self.q_flag is not None else False
        if t2_bad and q_bad:
            return "Unusual pattern + doesn't fit the model"
        if t2_bad:
            return "Unusual pattern (high T²)"
        if q_bad:
            return "Doesn't fit the model (high Q)"
        return ""
