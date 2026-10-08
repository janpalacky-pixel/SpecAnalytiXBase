# src/modules/data_analysis/automated_baseline_manager.py

import time

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.ndimage import grey_erosion, grey_dilation
from scipy.interpolate import BSpline
from src.modules.utils.app_logger import get_logger
from src.modules.utils.progress_utils import OperationCancelled, notify_progress
from src.modules.utils.correction_history import append_correction_history
from src.modules.utils.parallel_utils import (
    describe_worker_limits, resolve_worker_count, run_in_process_pool)
logger = get_logger(__name__)

# Display name of every algorithm in the correction history. An unknown
# algorithm name falls back to ALS (and its label), as it always has.
_ALGORITHM_LABELS = {
    'als': 'ALS', 'airpls': 'airPLS', 'arpls': 'arPLS', 'iarpls': 'iarPLS',
    'aspls': 'asPLS', 'drpls': 'drPLS', 'psalsa': 'psalsa',
    'imodpoly': 'I-ModPoly', 'morphological': 'Morphological Opening',
    'mpls': 'mpls', 'mollification': 'Morphology + Mollification',
    'mpspline': 'mpspline', 'jbcd': 'jbcd',
}

# 'auto' processing mode: how many spectra are timed serially first, the
# shortest remaining job for which parallel processing is considered at
# all, and the (conservative) time it takes to start the worker processes.
_AUTO_CALIBRATION_SPECTRA = 3
_AUTO_MIN_SERIAL_SECONDS = 6.0
_POOL_STARTUP_SECONDS = 4.0

# Shortest time (seconds) between two reports to the progress callable.
_PROGRESS_MIN_INTERVAL = 0.05


class AutomatedBaselineManager:
    """
    Business logic for automated baseline correction. Twelve algorithms,
    selected via apply_correction()'s params['algorithm']:
      - 'als' (default): Asymmetric Least Squares (Eilers & Boelens).
      - 'airpls': adaptive iteratively reweighted penalized least squares
        (Zhang, Chen & Liang, 2010) — needs no asymmetry parameter and
        typically needs a smaller lambda than ALS for the same spectrum.
      - 'arpls': asymmetrically reweighted penalized least squares
        (Baek, Park, Ahn & Choo, 2015) — also needs no asymmetry
        parameter; uses the same second-order penalty/lambda scale as
        ALS (unlike airPLS's first-order penalty), but re-weights points
        each iteration via a logistic function of the residuals instead
        of ALS's fixed p split or airPLS's exponential growth, which the
        reference reports is somewhat more robust on noisy baselines.
      - 'iarpls': improved arPLS (Ye, Tian, Wei & Li, 2020) — same
        second-order-penalty Whittaker solver and λ scale as arPLS,
        but a different per-iteration weight formula (an
        iteration-sharpened ISRU-style curve rather than arPLS's fixed
        logistic one) that specifically fixes arPLS's tendency to
        overestimate the baseline under small peaks in noisy data (see
        calculate_iarpls_baseline).
      - 'aspls': adaptive smoothness penalized least squares (Zhang,
        Tang, Tong, Wang, Wang, Lv, Tang & Wang, 2020) -- another arPLS
        derivative: same second-order penalty family and a similar
        logistic weight update, but the smoothness penalty itself is no
        longer a single scalar lambda applied uniformly -- it's scaled
        point-by-point by an adaptive weight alpha (recomputed each
        iteration from the current residual's magnitude relative to its
        own maximum), letting the fit stay stiff under confidently-flat
        baseline regions while relaxing near features it isn't sure
        about yet (see calculate_aspls_baseline).
      - 'drpls': doubly reweighted penalized least squares (Xu, Liu,
        Cai & Yang, 2019) -- the most structurally different of the
        arPLS-family additions: on top of arPLS's usual second-order
        smoothness penalty and logistic-style weighting, it adds an
        unweighted first-order penalty term (discourages a sloped, not
        just curved, baseline) and a second tunable parameter eta
        (0-1) that scales how much the second-order penalty itself
        gets relaxed under high-weight (peak) regions -- letting peak
        and non-peak areas be smoothed differently in a way none of
        the single-lambda methods above can (see
        calculate_drpls_baseline).
      - 'psalsa': peaked signal's asymmetric least squares algorithm
        (Oller-Moreno, Pardo, Jimenez-Soto, Samitier & Marco, 2014) --
        same second-order-penalty Whittaker solver and lambda scale as
        ALS, but replaces ALS's hard p/(1-p) split with an exponential
        decay on the weight of any point above the current baseline fit
        (points at or below it still get the fixed 1-p weight) -- tall
        peaks are suppressed smoothly rather than being all-or-nothing
        rejected, which the reference reports allows using a higher
        (less extreme) asymmetry p than plain ALS while still fitting
        noisy data well (see calculate_psalsa_baseline).
      - 'imodpoly': Improved Modified Polynomial fit (Zhao, Lui, McLean
        & Zeng, 2007) — fits a single low-order polynomial rather than a
        Whittaker-smoothed curve, with its own iterative peak-rejection
        and a residual-standard-deviation-based stopping rule (see
        calculate_imodpoly_baseline). Its own 'poly_order' parameter
        replaces 'lambda'/'p'; not a member of the Whittaker family
        above.
      - 'morphological': adaptive morphological opening (Perez-Pueyo,
        Soneira & Ruiz-Moreno, 2010) — order-statistics (min/max) based,
        not a regularized fit at all, so it has no tunable smoothness,
        asymmetry, or polynomial-order parameter whatsoever; the
        structuring-element size that the other three methods would ask
        the user to choose is instead grown automatically until the
        result stops changing (see calculate_morphological_baseline).
      - 'mpls': morphological weighted penalized least squares (Li,
        Zhan, Wang, Huang, Xu, Zhang, Zheng, Liang & Wang, 2013) -- a
        genuine hybrid of the previous two ideas rather than another
        arPLS derivative: it reuses 'morphological' opening's own
        min/max machinery to locate a handful of "anchor points" it
        trusts as pure baseline, then solves ALS's own second-order
        Whittaker system exactly once, weighted so those anchor points
        dominate the fit. No iterative reweighting loop at all -- the
        paper's whole premise is that morphology alone already tells
        you where the baseline is, without guessing a residual
        threshold iteration after iteration the way every other
        Whittaker-family method above does (see
        calculate_mpls_baseline).
      - 'mollification': morphology + mollification (Koch, Suhr, Roth
        & Meinhardt-Wollweber, 2017, introducing the mollifier-kernel
        idea; refined by Chen, Xu & Broderick, 2019, adding the
        "averaging" step below) -- a third hybrid, and the only method
        here with no system of equations to solve at all, Whittaker or
        otherwise: each iteration takes the element-wise minimum of the
        original spectrum against the average of a morphological
        closing and opening of the *current* baseline estimate, then
        smooths that candidate with a fixed, compactly-supported
        "mollifier" kernel (a standard bump function from real
        analysis) via convolution. Repeated until the baseline stops
        changing appreciably. Like Morphological Opening, it has no
        smoothness or asymmetry parameter to tune -- its structuring-
        element window is grown automatically the same way (see
        calculate_mollification_baseline).
      - 'mpspline': morphology-based penalized spline (Gonzalez-Vidal,
        Perez-Pueyo & Soneira, 2017) -- shaped exactly like 'mpls':
        morphology finds a handful of anchor points, then a single
        non-iterative weighted least-squares solve is fit through
        them, no reweighting loop. The fit itself is a cubic penalized
        spline (a fixed ~100-basis-function B-spline regularized by a
        difference penalty on its own coefficients) rather than mpls's
        direct Whittaker smoother (one coefficient per data point), so
        it needs far fewer effective degrees of freedom for a given
        spectrum length -- the appeal for large spectra, at the cost
        of a genuinely different fitting mechanism (see
        calculate_mpspline_baseline and _pspline_fit).
    All twelve support region exclusion via params['fitting_ranges'] +
    params['invert_regions'], applied identically by apply_correction.
    The dialog's "Region Shortcuts" checkboxes (see
    src/modules/data_analysis/baseline_region_presets.py) are pure UI
    convenience on top of that same mechanism — by the time settings
    reach this class, a preset-added range is indistinguishable from a
    manually drawn one.
    """

    def __init__(self):
        # Labels of any spectra whose correction failed on the most
        # recent apply_correction() call — see that method's docstring.
        self.failed_labels = []
        # What the most recent apply_correction() actually did (processing
        # mode, workers, seconds) -- see run_summary().
        self.last_run_info = None

    def calculate_als_baseline(self, y, lam, p, niter=10, exclude_indices=None):
        """
        Calculates a baseline using ALS, ignoring specified regions.
        This version is more robust against numerical errors.
        """
        L = len(y)
        D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(L - 2, L))
        D = lam * D.transpose().dot(D)
        
        w = np.ones(L)
        
        try:
            for i in range(niter):
                W = sparse.spdiags(w, 0, L, L)
                Z = W + D
                z = spsolve(Z, w * y)
                
                w_new = p * (y > z) + (1 - p) * (y <= z)
                
                # Enforce exclusion regions in every iteration
                if exclude_indices is not None:
                    w = w_new * ~exclude_indices
                else:
                    w = w_new
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during ALS fitting: {e}")
            return np.full_like(y, np.nan) # Return NaN array on failure

        # If regions were excluded, we must interpolate the baseline through them
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            
            # We need at least 2 points to interpolate across the whole spectrum
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan) # Cannot interpolate
                
            # Perform linear interpolation to fill the gaps in the baseline
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def _whittaker_smooth(self, y, w, lam, differences=1):
        """
        Penalized least-squares smoothing used inside
        calculate_airpls_baseline's iterative reweighting loop below
        (Eilers, 2003 smoothing step, as used by Zhang/Chen/Liang's
        airPLS). Not used by calculate_als_baseline above, which solves
        its own, differently-weighted least-squares system directly.
        """
        L = len(y)
        E = sparse.eye(L, format='csc')
        for _ in range(differences):
            E = E[1:] - E[:-1]

        W = sparse.diags(w, 0, shape=(L, L))
        A = sparse.csc_matrix(W + lam * E.transpose().dot(E))
        B = sparse.csc_matrix(W.dot(y.reshape(-1, 1)))

        background = spsolve(A, B)
        return np.asarray(background).ravel()

    def calculate_airpls_baseline(self, y, lam, porder=1, itermax=20, exclude_indices=None):
        """
        Calculates a baseline using airPLS (adaptive iteratively
        reweighted penalized least squares), ignoring specified regions
        the same way calculate_als_baseline does.

        Adapted from the reference airPLS.py implementation (Renato
        Lombardo, 2014; https://github.com/zmzhang/airPLS), itself a
        Python port of the original R/MATLAB code by Zhang & Liang. Two
        differences from that reference: (1) exclude_indices support,
        applied at the same point in the loop as calculate_als_baseline's
        own exclude_indices handling (weights zeroed there from the
        second iteration onward, then the baseline linearly interpolated
        through those points afterward), so user-selected fitting ranges
        and the water-band preset work identically for both algorithms;
        (2) the same try/except-then-NaN failure contract as
        calculate_als_baseline, so apply_correction() can detect and
        report a failed fit exactly like it already does for ALS,
        instead of letting the reference's occasional empty-weight edge
        case (no points left with a negative residual) propagate as an
        uncaught exception.

        Unlike ALS, airPLS has no asymmetry parameter (p) — the weighting
        that favours points below the fitted curve is derived adaptively
        from the residuals themselves each iteration.

        Reference: Z.-M. Zhang, S. Chen, and Y.-Z. Liang, "Baseline
        correction using adaptive iteratively reweighted penalized least
        squares." Analyst 135(5), 1138-1146 (2010).
        """
        L = len(y)
        w = np.ones(L)
        z = y.copy()

        try:
            for i in range(1, itermax + 1):
                z = self._whittaker_smooth(y, w, lam, porder)
                d = y - z
                neg = d < 0
                dssn = np.abs(d[neg].sum())

                if dssn < 0.001 * np.abs(y).sum() or i == itermax:
                    break

                # Points above the fitted curve (d >= 0) are treated as
                # peaks and excluded (weight 0); points below it get an
                # exponentially growing weight as iterations proceed, so
                # the fit is pulled down toward the noise floor rather
                # than the peak tops. Endpoints get a matching boundary
                # weight so the fit doesn't drift at the edges.
                w_new = np.zeros(L)
                w_new[neg] = np.exp(i * np.abs(d[neg]) / dssn)
                edge_value = np.exp(i * d[neg].max() / dssn)
                w_new[0] = edge_value
                w_new[-1] = edge_value

                w = w_new * ~exclude_indices if exclude_indices is not None else w_new
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during airPLS fitting: {e}")
            return np.full_like(y, np.nan)

        # Same post-hoc interpolation through excluded regions as
        # calculate_als_baseline — see that method for why.
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan)
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def calculate_arpls_baseline(self, y, lam, itermax=50, ratio=0.05, exclude_indices=None):
        """
        Calculates a baseline using arPLS (asymmetrically reweighted
        penalized least squares), ignoring specified regions the same
        way calculate_als_baseline/calculate_airpls_baseline do.

        Reuses the same Whittaker-smoothing solver as
        calculate_airpls_baseline (_whittaker_smooth), but with a
        second-order difference penalty (differences=2) — the same
        order calculate_als_baseline's own D matrix uses, and the order
        the original arPLS paper's penalty is built on — rather than
        airPLS's first-order penalty here, which is why arPLS wants a
        lambda on ALS's scale, not airPLS's much smaller one. Weighting
        is a different rule again: each iteration, every point is
        re-weighted by a logistic function of how far its residual sits
        below a data-driven threshold (2*std - mean of the *negative*
        residuals), rather than ALS's fixed p split or airPLS's
        exponential-growth weighting. Like airPLS, there is no asymmetry
        parameter (p) — the weighting is derived adaptively from the
        residuals each iteration. Convergence is checked directly (the
        relative change in the weight vector, via `ratio`) rather than
        always running to itermax, since the logistic weights tend to
        stabilize well before typical iteration caps.

        exclude_indices handling and the try/except-then-NaN failure
        contract mirror calculate_airpls_baseline exactly, for the same
        reasons (see that method's docstring) — weights on excluded
        points are zeroed from the second iteration onward, then the
        baseline is linearly interpolated through those points
        afterward, so user-selected fitting ranges and Region Shortcuts
        work identically across all three algorithms.

        Reference: S.-J. Baek, A. Park, Y.-J. Ahn, and J. Choo,
        "Baseline correction using asymmetrically reweighted penalized
        least squares smoothing." Analyst 140(1), 250-257 (2015).
        """
        L = len(y)
        w = np.ones(L)
        z = y.copy()

        try:
            for i in range(itermax):
                z = self._whittaker_smooth(y, w, lam, differences=2)
                d = y - z
                neg = d < 0

                if not np.any(neg):
                    # No negative residuals left to derive the threshold
                    # from -- the fit already sits at or below every
                    # point, so there's nothing left to reweight toward.
                    break

                m = np.mean(d[neg])
                s = np.std(d[neg])
                if s == 0:
                    break

                # Clip the exponent -- large negative residuals under
                # a tall peak can otherwise overflow exp() (harmless,
                # since 1/(1+inf) is exactly the 0 weight we want
                # there, but it prints a RuntimeWarning every call).
                exponent = np.clip(2.0 * (d - (2.0 * s - m)) / s, -500.0, 500.0)
                w_new = 1.0 / (1.0 + np.exp(exponent))
                w_new = w_new * ~exclude_indices if exclude_indices is not None else w_new

                denom = np.linalg.norm(w)
                converged = denom > 0 and np.linalg.norm(w_new - w) / denom < ratio
                w = w_new
                if converged:
                    break
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during arPLS fitting: {e}")
            return np.full_like(y, np.nan)

        # Same post-hoc interpolation through excluded regions as
        # calculate_als_baseline/calculate_airpls_baseline -- see
        # calculate_als_baseline for why.
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan)
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def calculate_iarpls_baseline(self, y, lam, itermax=100, ratio=0.001, exclude_indices=None):
        """
        Calculates a baseline using iarPLS (improved asymmetrically
        reweighted penalized least squares), ignoring specified regions
        the same way calculate_arpls_baseline does. Fixes arPLS's
        documented tendency to overestimate the baseline under small
        peaks in noisy data.

        Reuses the same second-order-penalty Whittaker solver as
        calculate_arpls_baseline (same _whittaker_smooth call, same λ
        scale -- ALS's, not airPLS's) -- only the per-iteration weight
        formula changes. Where arPLS thresholds each residual against
        2*std - mean of the negative residuals and squashes it through a
        logistic function, iarPLS thresholds against 2*std alone (no
        mean term) and squashes it through an ISRU-style function
        (x / sqrt(1+x^2), the paper's own "ISRU weighting function")
        scaled by exp(min(iteration, 100)) -- an iteration-dependent
        term that reshapes the weighting curve from gentle/logistic-like
        at low iterations to a near step-function at high iterations,
        which is specifically what stops it from overestimating under
        small peaks the way arPLS can (Ye et al.'s own stated mechanism,
        Figure 1). The exponent is capped at iteration 100 since the
        curve is already effectively a step function well before then,
        matching the choice made by the open-source implementation this
        was cross-checked against -- unlike arPLS's raw exp() weighting,
        this ISRU form is self-normalizing and never overflows, so no
        separate exponent clipping is needed here.

        exclude_indices handling, the try/except-then-NaN failure
        contract, and the post-hoc interpolation through excluded points
        all mirror calculate_arpls_baseline exactly -- see that method's
        docstring for the full reasoning.

        Reference: J. Ye, Z. Tian, H. Wei, and Y. Li, "Baseline
        correction method based on improved asymmetrically reweighted
        penalized least squares for the Raman spectrum." Applied
        Optics 59(34), 10933-10943 (2020).
        """
        L = len(y)
        w = np.ones(L)
        z = y.copy()

        try:
            for i in range(1, itermax + 1):
                z = self._whittaker_smooth(y, w, lam, differences=2)
                d = y - z
                neg = d < 0

                if np.count_nonzero(neg) < 2:
                    # Fewer than 2 negative-residual points makes the
                    # sample standard deviation below (ddof=1) undefined
                    # -- same early-exit condition used by the reference
                    # implementation this was checked against.
                    break

                s = np.std(d[neg], ddof=1)
                if s == 0:
                    break

                growth = np.exp(min(i, 100))
                inner = (growth / s) * (d - 2.0 * s)
                w_new = 0.5 * (1.0 - inner / np.sqrt(1.0 + inner ** 2))
                w_new = w_new * ~exclude_indices if exclude_indices is not None else w_new

                denom = np.linalg.norm(w)
                converged = denom > 0 and np.linalg.norm(w_new - w) / denom < ratio
                w = w_new
                if converged:
                    break
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during iarPLS fitting: {e}")
            return np.full_like(y, np.nan)

        # Same post-hoc interpolation through excluded regions as
        # calculate_arpls_baseline -- see calculate_als_baseline for why.
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan)
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def calculate_aspls_baseline(self, y, lam, itermax=100, ratio=0.001, asymmetric_coef=0.5, exclude_indices=None):
        """
        Calculates a baseline using asPLS (adaptive smoothness penalized
        least squares), ignoring specified regions the same way
        calculate_arpls_baseline does.

        Unlike every other Whittaker-family method here, the smoothness
        penalty itself isn't a single scalar lambda applied uniformly --
        it's scaled point-by-point by an adaptive diagonal alpha, so the
        linear system solved each iteration is
        (W + diag(alpha) @ lam*D^T D) z = W y (D the second-order
        difference matrix, built directly here rather than through
        _whittaker_smooth, since that helper has no alpha-scaling hook).
        alpha starts at 1 everywhere (a plain Whittaker solve on the
        first pass) and is then recomputed after every iteration as
        alpha_i = |residual_i| / max(|residual|) -- points near the
        current fit (confidently baseline) get pulled toward alpha ~ 0,
        loosening the penalty there, while points with a large residual
        (peaks, or wherever the fit is still unsure) keep alpha closer
        to 1 and stay stiffly smoothed. Weights use the same general
        logistic shape as calculate_arpls_baseline's, but simpler:
        w = 1 / (1 + exp(k*(residual - s)/s)), thresholded at s (the
        standard deviation of the negative residuals alone, no mean
        term) rather than arPLS's 2*std - mean. asymmetric_coef (k)
        defaults to 0.5 here rather than the reference paper's own
        value of 2 -- matching the default used by the open-source
        implementations this was cross-checked against, which found 0.5
        fits noisy data closer to the paper's own reported results
        (Table 2 / Figure 5) than the paper's stated 2 does. The
        exponent is clipped the same way calculate_arpls_baseline's is,
        to avoid a harmless-but-noisy exp() overflow warning under a
        tall peak's large residual.

        exclude_indices handling, the try/except-then-NaN failure
        contract, and the post-hoc interpolation through excluded points
        all mirror calculate_arpls_baseline exactly -- see that method's
        docstring for the full reasoning.

        Reference: F. Zhang, X. Tang, A. Tong, B. Wang, J. Wang, Y. Lv,
        C. Tang, and J. Wang, "Baseline correction for infrared spectra
        using adaptive smoothness parameter penalized least squares
        method." Spectroscopy Letters 53(3), 222-233 (2020).
        """
        L = len(y)
        E = sparse.eye(L, format='csc')
        D = E[2:] - 2 * E[1:-1] + E[:-2]
        DD = lam * D.transpose().dot(D)

        w = np.ones(L)
        alpha = np.ones(L)
        z = y.copy()

        try:
            for _ in range(itermax):
                W = sparse.diags(w, 0, shape=(L, L))
                A = sparse.diags(alpha, 0, shape=(L, L))
                lhs = sparse.csc_matrix(W + A.dot(DD))
                rhs = sparse.csc_matrix(W.dot(y.reshape(-1, 1)))
                z = np.asarray(spsolve(lhs, rhs)).ravel()

                d = y - z
                neg = d < 0
                if np.count_nonzero(neg) < 2:
                    # Same early-exit condition as calculate_arpls_baseline
                    # -- too few negative-residual points to build a
                    # reliable threshold from.
                    break

                s = np.std(d[neg], ddof=1)
                if s == 0:
                    break

                exponent = np.clip(asymmetric_coef * (d - s) / s, -500.0, 500.0)
                w_new = 1.0 / (1.0 + np.exp(exponent))
                w_new = w_new * ~exclude_indices if exclude_indices is not None else w_new

                denom = np.linalg.norm(w)
                converged = denom > 0 and np.linalg.norm(w_new - w) / denom < ratio
                w = w_new
                if converged:
                    break

                abs_d = np.abs(d)
                max_abs_d = abs_d.max()
                if max_abs_d > 0:
                    alpha = abs_d / max_abs_d
                # A perfectly flat residual (max_abs_d == 0) leaves alpha
                # unchanged for the next pass -- nothing left to adapt to.
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during asPLS fitting: {e}")
            return np.full_like(y, np.nan)

        # Same post-hoc interpolation through excluded regions as
        # calculate_arpls_baseline -- see calculate_als_baseline for why.
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan)
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def calculate_drpls_baseline(self, y, lam, eta=0.5, itermax=50, ratio=0.001, exclude_indices=None):
        """
        Calculates a baseline using drPLS (doubly reweighted penalized
        least squares), ignoring specified regions the same way
        calculate_arpls_baseline does.

        The most structurally different of the arPLS-family additions
        here: instead of a single second-order-penalty Whittaker solve
        with a reweighted diagonal (calculate_arpls_baseline/
        calculate_iarpls_baseline/calculate_aspls_baseline's shared
        pattern), each iteration solves
        (P1 + Pn + W - eta*W@Pn) z = W y, where Pn = lam*D2^T D2 is the
        usual second-order penalty, P1 = D1^T D1 (D1 the first-order
        difference matrix, unweighted -- no separate lambda on this
        term) adds a mild penalty against an overall *sloped* baseline
        on top of Pn's penalty against curvature, and the eta*W@Pn term
        relaxes the second-order penalty itself in proportion to how
        strongly a point is currently weighted as a peak (W) -- letting
        peak and non-peak regions be smoothed differently in a way none
        of the single-lambda Whittaker methods above can. Built
        directly here rather than through _whittaker_smooth, since that
        helper has no hook for either the extra P1 term or eta's
        interaction with W.

        Weighting is a softsign-based variant of arPLS's own logistic
        rule, using the identical threshold (2*std - mean of the
        *negative* residuals) but with an iteration-sharpened
        prefactor, the same exp(min(iteration, 100)) term
        calculate_iarpls_baseline uses:
        w = 0.5*(1 - g/(1 + |g|)) where
        g = (exp(min(i, 100))/s)*(d - (2s - m)). Like iarPLS's ISRU
        curve, softsign (x/(1+|x|)) is self-normalizing and never
        overflows, so -- unlike calculate_arpls_baseline's raw exp()
        weighting -- no separate exponent clipping is needed here
        either.

        exclude_indices handling, the try/except-then-NaN failure
        contract, and the post-hoc interpolation through excluded points
        all mirror calculate_arpls_baseline exactly -- see that method's
        docstring for the full reasoning.

        Reference: D. Xu, S. Liu, Y. Cai, and C. Yang, "Baseline
        correction method based on doubly reweighted penalized least
        squares." Applied Optics 58(14), 3913-3920 (2019).
        """
        L = len(y)
        E = sparse.eye(L, format='csc')
        D1 = E[1:] - E[:-1]
        P1 = D1.transpose().dot(D1)
        D2 = E[2:] - 2 * E[1:-1] + E[:-2]
        Pn = lam * D2.transpose().dot(D2)

        w = np.ones(L)
        z = y.copy()

        try:
            for i in range(1, itermax + 1):
                W = sparse.diags(w, 0, shape=(L, L))
                A = sparse.csc_matrix(P1 + Pn + W - eta * W.dot(Pn))
                B = sparse.csc_matrix(W.dot(y.reshape(-1, 1)))
                z = np.asarray(spsolve(A, B)).ravel()

                d = y - z
                neg = d < 0
                if np.count_nonzero(neg) < 2:
                    # Same early-exit condition as calculate_arpls_baseline
                    # -- too few negative-residual points to build a
                    # reliable threshold from.
                    break

                m = np.mean(d[neg])
                s = np.std(d[neg], ddof=1)
                if s == 0:
                    break

                growth = np.exp(min(i, 100))
                inner = (growth / s) * (d - (2.0 * s - m))
                w_new = 0.5 * (1.0 - inner / (1.0 + np.abs(inner)))
                w_new = w_new * ~exclude_indices if exclude_indices is not None else w_new

                denom = np.linalg.norm(w)
                converged = denom > 0 and np.linalg.norm(w_new - w) / denom < ratio
                w = w_new
                if converged:
                    break
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during drPLS fitting: {e}")
            return np.full_like(y, np.nan)

        # Same post-hoc interpolation through excluded regions as
        # calculate_arpls_baseline -- see calculate_als_baseline for why.
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan)
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def calculate_psalsa_baseline(self, y, lam, p=0.5, k=None, itermax=50, ratio=0.001, exclude_indices=None):
        """
        Calculates a baseline using psalsa (peaked signal's asymmetric
        least squares algorithm), ignoring specified regions the same
        way calculate_als_baseline does.

        Reuses the same second-order-penalty Whittaker solver as
        calculate_arpls_baseline/calculate_iarpls_baseline
        (_whittaker_smooth, differences=2) -- the same penalty order,
        and therefore the same lambda scale, as calculate_als_baseline's
        own hand-rolled solve. Where ALS gives every point above the
        current fit the same fixed weight p regardless of how far above
        it sits, psalsa instead decays that weight exponentially with
        the residual's size: w = p * exp(-residual / k) for points above
        the baseline (residual = y - z > 0), and the fixed 1 - p for
        points at or below it. A tall peak's weight collapses toward 0
        almost immediately while a small bump keeps a meaningful
        fraction of p -- which is what lets p itself be set less
        aggressively (e.g. 0.5) than plain ALS typically needs (e.g.
        0.01) while still suppressing real peaks, per the reference. k
        sets the residual scale the decay runs on -- roughly "how tall
        counts as a peak" -- and defaults to one-tenth of the spectrum's
        own standard deviation when not given, matching the default used
        by the open-source implementation this was cross-checked
        against. Convergence is checked the same way as
        calculate_arpls_baseline/calculate_iarpls_baseline (relative
        change in the weight vector via `ratio`), since unlike ALS's
        fixed p/(1-p) split, psalsa's weights do settle rather than
        oscillate indefinitely.

        exclude_indices handling, the try/except-then-NaN failure
        contract, and the post-hoc interpolation through excluded points
        all mirror calculate_als_baseline/calculate_arpls_baseline --
        see calculate_als_baseline's docstring for the full reasoning.

        Reference: S. Oller-Moreno, A. Pardo, J. M. Jimenez-Soto,
        J. Samitier, and S. Marco, "Adaptive Asymmetric Least Squares
        baseline estimation for analytical instruments." 2014 IEEE 11th
        International Multi-Conference on Systems, Signals & Devices
        (SSD14), 1-5 (2014).
        """
        L = len(y)
        if k is None:
            k = np.std(y) / 10.0
        w = np.ones(L)
        z = y.copy()

        try:
            if k == 0:
                # A perfectly flat input has nothing for the exponential
                # decay to scale against -- fall back to a plain fixed
                # p/(1-p) split (k's role becomes moot: every residual
                # is 0 too, so there's no peak to suppress anyway).
                k = 1.0
            for _ in range(itermax):
                z = self._whittaker_smooth(y, w, lam, differences=2)
                d = y - z
                above = d > 0

                w_new = np.full(L, 1.0 - p)
                w_new[above] = p * np.exp(-d[above] / k)
                w_new = w_new * ~exclude_indices if exclude_indices is not None else w_new

                denom = np.linalg.norm(w)
                converged = denom > 0 and np.linalg.norm(w_new - w) / denom < ratio
                w = w_new
                if converged:
                    break
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during psalsa fitting: {e}")
            return np.full_like(y, np.nan)

        # Same post-hoc interpolation through excluded regions as
        # calculate_als_baseline -- see that method for why.
        if exclude_indices is not None and np.any(exclude_indices):
            included_indices = np.where(~exclude_indices)[0]
            if len(included_indices) < 2:
                logger.warning("Warning: Not enough included points to create a reliable baseline.")
                return np.full_like(y, np.nan)
            z = np.interp(np.arange(L), included_indices, z[included_indices])

        return z

    def calculate_imodpoly_baseline(self, x, y, poly_order=5, itermax=100, tol=0.05, exclude_indices=None):
        """
        Calculates a baseline using I-ModPoly (Improved Modified
        Multi-polynomial Fit), ignoring specified regions the same way
        the Whittaker-family methods above do -- but structurally this
        is not one of them: it fits a single global polynomial rather
        than a locally-penalized smooth curve, so it has no lambda and
        instead takes a polynomial order.

        Each iteration: fit a degree-`poly_order` polynomial by least
        squares, then rebuild the working signal for the next fit --
        points sitting within one residual standard deviation of the
        current fit keep their own value, points further above it are
        pulled down to the fit itself, so real Raman peaks stop dragging
        the polynomial upward the way they would with a plain unweighted
        fit. On top of that, the very first iteration also permanently
        drops any point more than one residual standard deviation above
        that initial fit -- Zhao et al.'s "peak-removal procedure during
        the first iteration" -- before the per-iteration reconstruction
        rule above starts running on what's left. Iteration stops once
        the residual standard deviation changes by less than `tol`
        (relative, default 5%) between iterations -- the paper's own
        automated cutoff -- or after itermax iterations, whichever comes
        first.

        Re-implemented from the algorithm's own description (Zhao et
        al. 2007, building on the base polynomial method of Lieber &
        Mahadevan-Jansen 2003), cross-checked step-for-step against an
        independent open-source implementation of the same published
        algorithm (michaelstchen/modPolyFit on GitHub, MIT-licensed,
        unrelated to any lab software) rather than derived from it --
        that implementation is itself a direct port of Zhao et al.'s
        paper, used here only to verify the iteration order and exact
        thresholding comparisons. x is used directly (not just point
        index) so the polynomial is a real function of wavenumber, like
        every other polynomial fit elsewhere in this codebase; it's
        rescaled internally to zero mean/unit variance purely for
        numerical conditioning at typical cm-1-scale wavenumber ranges
        and higher polynomial orders -- an implementation detail with no
        effect on the returned baseline, not part of the published
        algorithm.

        Reference: J. Zhao, H. Lui, D. I. McLean, and H. Zeng,
        "Automated autofluorescence background subtraction algorithm
        for biomedical Raman spectroscopy." Applied Spectroscopy 61(11),
        1225-1232 (2007). Builds on: C. A. Lieber and A.
        Mahadevan-Jansen, "Automated method for subtraction of
        fluorescence from biological Raman spectra." Applied
        Spectroscopy 57(11), 1363-1367 (2003).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        L = len(y)

        include_mask = ~exclude_indices if exclude_indices is not None else np.ones(L, dtype=bool)
        if np.count_nonzero(include_mask) < poly_order + 1:
            logger.warning(
                "Warning: Not enough included points to fit a "
                f"degree-{poly_order} polynomial.")
            return np.full_like(y, np.nan)

        # Numerical-conditioning rescale only -- see docstring. Applied
        # to the full x range once, up front, so the same linear map is
        # used for every fit/evaluation below, excluded points included.
        x_offset = x.mean()
        x_spread = x.std()
        x_norm_full = (x - x_offset) / x_spread if x_spread > 0 else (x - x_offset)

        x_fit = x_norm_full[include_mask]
        y_work = y[include_mask].copy()

        dev_prev = 0.0
        first_iter = True
        coeffs = None

        try:
            for _ in range(itermax):
                coeffs = np.polyfit(x_fit, y_work, poly_order)
                fitted = np.polyval(coeffs, x_fit)

                residual = y_work - fitted
                dev_curr = np.std(residual)
                if dev_curr == 0:
                    break

                if first_iter:
                    # One-time peak-removal pass (see docstring).
                    keep = y_work <= fitted + dev_curr
                    if np.count_nonzero(keep) < poly_order + 1:
                        logger.warning(
                            "Warning: Not enough included points left "
                            "after peak removal to fit a "
                            f"degree-{poly_order} polynomial.")
                        return np.full_like(y, np.nan)
                    x_fit = x_fit[keep]
                    y_work = y_work[keep]
                    fitted = fitted[keep]
                    first_iter = False

                # Reconstruct the working signal for the next fit.
                y_work = np.where(y_work < fitted + dev_curr, y_work, fitted)

                converged = abs((dev_curr - dev_prev) / dev_curr) <= tol
                dev_prev = dev_curr
                if converged:
                    break
        except Exception as e:
            logger.error(f"Warning: Linear algebra error during I-ModPoly fitting: {e}")
            return np.full_like(y, np.nan)

        # The fitted polynomial is one smooth function defined over the
        # whole rescaled x range, so -- unlike the Whittaker-family
        # methods above -- no post-hoc interpolation through excluded
        # points is needed: just evaluate it at every original x.
        return np.polyval(coeffs, x_norm_full)

    def calculate_morphological_baseline(self, y, itermax=300, exclude_indices=None):
        """
        Calculates a baseline using adaptive morphological opening,
        ignoring specified regions the same way the other
        calculate_*_baseline methods do -- but this one shares none of
        their machinery: it's an order-statistics (min/max) method, not
        a regularized least-squares fit, and unlike every other
        algorithm in this class it has no tunable smoothness/asymmetry/
        order parameter at all. The structuring-element size a user
        would otherwise have to pick is instead grown automatically
        until the result stops changing, per the reference below.

        Erosion e_Y(f)(x) and dilation d_Y(f)(x) are the min/max of f
        over a flat window of width Y centered at x; opening is erosion
        followed by dilation with the same window, c_Y(f) = d_Y[e_Y(f)].
        Starting from a 3-point window, the window is grown by 2 points
        (odd sizes: 3, 5, 7, ...) and the opening recomputed each time;
        once three consecutive openings come out exactly equal, growth
        stops and the smallest of those three window sizes is the
        "optimal" one (the reference reports this is how the algorithm
        converges automatically, with no window size to choose by
        hand). That optimal opening is then refined to correct for the
        band-shape distortion a plain opening can introduce: c'(f) =
        (d[c(f)] + e[c(f)]) / 2, dilating and eroding the *opening*
        itself with the same optimal window, and the final baseline is
        the elementwise minimum of that average against the plain
        opening, c_opt(f) = min(c'(f), c(f)) -- taking whichever sits
        lower, since the correction step exists specifically to pull
        the curve back down where the plain opening drifted upward into
        a band.

        Three implementation details the reference paper doesn't
        specify, decided here rather than left ambiguous: (1) boundary
        handling for the sliding min/max windows uses edge-value
        replication (mode='nearest'), standard practice for 1-D
        morphological filters, avoiding the artificial dip/rise a
        wrap-around or zero-padded boundary would otherwise introduce
        at the spectrum's two ends; (2) the correction step's
        erosion/dilation reuse the same optimal window found by the
        growth loop, the most direct reading of "erosion and dilation
        of the opening"; (3) `itermax` caps the number of growth steps
        (window sizes tried) as a safety net -- exact equality between
        three consecutive openings is actually well-founded for real
        spectra (grey erosion/dilation only ever *select* an existing
        sample value, never compute a new one, so once growth reaches a
        window already wide enough to have captured the eventual
        limiting value at every point, further growth reproduces it
        bit-for-bit) but isn't mathematically guaranteed for arbitrary
        data, so growth stops at itermax and uses the widest opening
        reached so far rather than looping indefinitely.

        exclude_indices handling differs from the Whittaker-family
        methods' weight-zeroing: since morphological opening has no
        weighted fit to zero a point out of, excluded points are
        dropped from the working array entirely before the growth loop
        runs (so they can't set a window's min/max anywhere), and the
        converged baseline is then linearly interpolated back through
        them afterward -- same end contract (excluded points don't
        influence the fit; the returned baseline still covers every
        point) as calculate_als_baseline and the rest, just reached by
        removal instead of reweighting, since that's the only lever
        this algorithm has.

        Reference: R. Perez-Pueyo, M. J. Soneira, and S. Ruiz-Moreno,
        "Morphology-based automated baseline removal for Raman spectra
        of artistic pigments." Applied Spectroscopy 64(6), 595-600
        (2010).
        """
        y = np.asarray(y, dtype=float)
        L = len(y)

        include_mask = ~exclude_indices if exclude_indices is not None else np.ones(L, dtype=bool)
        included_indices = np.where(include_mask)[0]
        n = len(included_indices)
        if n < 3:
            logger.warning("Warning: Not enough included points for morphological opening.")
            return np.full_like(y, np.nan)

        y_work = y[included_indices]

        try:
            window = 3
            window_history = []
            opening_history = []
            optimal_window = None
            optimal_opening = None
            for _ in range(itermax):
                if window > n:
                    # Nothing left for a wider window to reveal.
                    break
                eroded = grey_erosion(y_work, size=window, mode='nearest')
                opening = grey_dilation(eroded, size=window, mode='nearest')
                window_history.append(window)
                opening_history.append(opening)
                if len(opening_history) >= 3:
                    a, b, c = opening_history[-3:]
                    if np.array_equal(a, b) and np.array_equal(b, c):
                        optimal_window = window_history[-3]
                        optimal_opening = a
                        break
                window += 2

            if optimal_opening is None:
                # Safety fallback (see docstring) -- use the widest
                # opening reached rather than the paper's exact-equality
                # convergence, which wasn't hit within the cap.
                optimal_window = window_history[-1]
                optimal_opening = opening_history[-1]

            # Refinement step: corrects for band-shape distortion in the
            # plain opening (see docstring).
            d_c = grey_dilation(optimal_opening, size=optimal_window, mode='nearest')
            e_c = grey_erosion(optimal_opening, size=optimal_window, mode='nearest')
            c_prime = (d_c + e_c) / 2.0
            c_opt = np.minimum(c_prime, optimal_opening)
        except Exception as e:
            logger.error(f"Warning: Error during morphological baseline fitting: {e}")
            return np.full_like(y, np.nan)

        if n == L:
            return c_opt

        # Same post-hoc interpolation through excluded points as
        # calculate_als_baseline -- see that method for why.
        return np.interp(np.arange(L), included_indices, c_opt)

    def calculate_mpls_baseline(self, y, lam=1e6, p=0.0, itermax=300, exclude_indices=None):
        """
        Calculates a baseline using mpls (morphological weighted
        penalized least squares), ignoring specified regions the same
        way calculate_morphological_baseline does -- exclusion is
        handled identically here since this method starts from that
        same morphological opening step.

        Two ideas combined into one baseline, rather than either used
        alone: (1) grow a structuring-element window exactly as
        calculate_morphological_baseline does (start at 3, widen by 2
        each step, stop once three consecutive openings agree exactly)
        to get a rough, order-statistics estimate of the baseline's
        shape; (2) instead of using that opening as the baseline
        directly, use it only to pick out a handful of trustworthy
        "anchor points" -- specifically, the index of the minimum
        y-value within each flat segment of the opening -- and solve
        ALS's own second-order-penalty Whittaker system, (W + lam*D^T
        D) z = W y, exactly once, with anchor points weighted 1-p and
        every other point weighted p. There is no iterative reweighting
        loop here at all, unlike every other Whittaker-family method in
        this class: the paper's central claim is that the morphology
        alone already identifies where the baseline is, so a single
        weighted solve suffices -- no residual-threshold guessing,
        iteration after iteration, the way ALS/airPLS/arPLS/etc. all
        need. p defaults to 0.0 (anchor points fully trusted, weight 1;
        every other point fully ignored, weight 0), matching both the
        paper's own default and the open-source implementation this was
        checked against; raising p lets the non-anchor points
        contribute to the fit too, rather than being weighted out
        entirely.

        The paper does not itself mandate a specific half-window search
        procedure for the opening step -- it treats window growth as an
        implementation detail, not part of its core contribution (the
        anchor-point-and-single-solve idea is). This reuses the exact
        same growth loop as calculate_morphological_baseline (Perez-
        Pueyo et al., 2010) rather than inventing a second, different
        heuristic, so the two methods agree on what "the" morphological
        opening of a given spectrum is.

        Flat-segment detection and anchor-point selection are carried
        over unchanged (variable names included) from the open-source
        implementation this was cross-checked against, since getting
        the off-by-one boundary logic exactly right matters more than
        writing it differently for its own sake: a value is a boundary
        of a flat run if exactly one of its two neighboring differences
        is zero, and consecutive boundary-pairs mark out each run,
        within which the minimum y-value becomes that run's anchor.

        Reference: Li, Z., Zhan, D., Wang, J., Huang, J., Xu, Q.,
        Zhang, Z., Zheng, Y., Liang, Y., & Wang, H. (2013).
        Morphological weighted penalized least squares for background
        correction. Analyst, 138(16), 4483-4492.
        """
        y = np.asarray(y, dtype=float)
        L = len(y)

        include_mask = ~exclude_indices if exclude_indices is not None else np.ones(L, dtype=bool)
        included_indices = np.where(include_mask)[0]
        n = len(included_indices)
        if n < 3:
            logger.warning("Warning: Not enough included points for mpls.")
            return np.full_like(y, np.nan)

        y_work = y[included_indices]

        try:
            window = 3
            window_history = []
            opening_history = []
            optimal_opening = None
            for _ in range(itermax):
                if window > n:
                    break
                eroded = grey_erosion(y_work, size=window, mode='nearest')
                opening = grey_dilation(eroded, size=window, mode='nearest')
                window_history.append(window)
                opening_history.append(opening)
                if len(opening_history) >= 3:
                    a, b, c = opening_history[-3:]
                    if np.array_equal(a, b) and np.array_equal(b, c):
                        optimal_opening = a
                        break
                window += 2

            if optimal_opening is None:
                # Same safety fallback as calculate_morphological_baseline:
                # use the widest opening reached rather than the paper's
                # exact-equality convergence, which wasn't hit within the cap.
                optimal_opening = opening_history[-1]

            # Anchor-point selection, carried over from the reference
            # implementation (see docstring): a boundary of a flat run in
            # the opening is a point where exactly one of its two
            # neighboring differences is zero; the minimum y-value within
            # each pair of consecutive boundaries becomes that run's
            # anchor point.
            padded = np.concatenate([optimal_opening[:1], optimal_opening, optimal_opening[-1:]])
            diff = np.diff(padded)
            boundary_mask = ((diff[1:] == 0) | (diff[:-1] == 0)) & ((diff[1:] != 0) | (diff[:-1] != 0))
            indices = np.flatnonzero(boundary_mask)

            if len(indices) < 2:
                # The opening has no internal flat-region boundaries at
                # all -- e.g. a perfectly flat or perfectly monotonic
                # spectrum, where morphology finds nothing to single out
                # as "more baseline" than anything else. Falling through
                # to the normal loop would leave w entirely at p (0.0 by
                # default), which under-determines the Whittaker solve's
                # null space and returns a near-zero baseline instead of
                # the correct one. Trusting every point equally (as if
                # the whole spectrum were one giant anchor) is the
                # reasonable fallback here, and recovers the input
                # exactly for both edge cases above.
                w = np.full(n, 1.0 - p)
            else:
                w = np.full(n, p)
                for previous_segment, next_segment in zip(indices[1::2], indices[2::2]):
                    anchor = np.argmin(y_work[previous_segment:next_segment + 1]) + previous_segment
                    w[anchor] = 1.0 - p

            z_included = self._whittaker_smooth(y_work, w, lam, differences=2)
        except Exception as e:
            logger.error(f"Warning: Error during mpls fitting: {e}")
            return np.full_like(y, np.nan)

        if n == L:
            return z_included

        return np.interp(np.arange(L), included_indices, z_included)

    def calculate_mollification_baseline(self, y, itermax=200, tol=1e-3, exclude_indices=None):
        """
        Calculates a baseline using morphology + mollification, ignoring
        specified regions the same way calculate_morphological_baseline
        and calculate_mpls_baseline do.

        The only method in this class with no system of equations to
        solve at all, Whittaker or otherwise -- it's pure order-statistics
        (min/max) plus a fixed convolution kernel, repeated until the
        result stops changing:

        1. Find a structuring-element window the same way
           calculate_morphological_baseline does (grow from 3 points by
           2 each step until three consecutive openings agree exactly).
           Neither reference paper below mandates a specific window-
           selection rule (Koch & Suhr's own abstract describes theirs
           as "three experimentally-determined parameters" rather than
           an automatic search), so this reuses the same well-tested
           growth loop as the other two morphological methods here
           rather than adding a third, different heuristic.
        2. Build a "mollifier" kernel -- not something invented for this
           algorithm, but a standard compactly-supported, infinitely
           smooth bump function from real analysis (a Friedrichs
           mollifier): over its own local coordinate x in (-1, 1),
           exp(-1 / (1 - x^2)), zero at and beyond |x| = 1, normalized
           to sum to 1 so convolving with it preserves the data's
           overall scale.
        3. Pad the spectrum on both ends (linear extrapolation from each
           edge's own local trend, one window's worth of points) so the
           convolution steps below don't distort the two ends.
        4. Starting from that padded spectrum as the first baseline
           estimate, repeat: take the morphological closing and opening
           of the *current* baseline estimate (same window as step 1),
           average the two, then take the element-wise minimum of that
           average against the (padded) original spectrum -- this is
           the "averaging" refinement Chen, Xu & Broderick's 2019 paper
           adds on top of Koch & Suhr's original 2017 method, and it's
           what keeps the estimate from drifting upward into real peaks
           over repeated iterations. Smooth that candidate with the
           mollifier kernel via convolution (itself edge-padded by
           reflection, to keep the convolution's own boundary from
           reintroducing the artifact step 3 removed) to get the next
           baseline estimate. Stop once the relative change in the
           baseline between iterations drops below tol, or after
           itermax iterations.
        5. Trim the padding back off before returning.

        References: (1) M. Koch, C. Suhr, B. Roth, and M.
        Meinhardt-Wollweber, "Iterative morphological and
        mollifier-based baseline correction for Raman spectra." Journal
        of Raman Spectroscopy 48(2), 336-342 (2017) -- introduces the
        morphology-plus-mollifier-kernel idea itself. (2) H. Chen, W.
        Xu, and N. G. R. Broderick, "An adaptive and fully automated
        baseline correction method for Raman spectroscopy based on
        morphological operations and mollification." Applied
        Spectroscopy 73(3), 284-293 (2019) -- adds the closing/opening
        "averaging" step used above, which this implementation follows.
        """
        y = np.asarray(y, dtype=float)
        L = len(y)

        include_mask = ~exclude_indices if exclude_indices is not None else np.ones(L, dtype=bool)
        included_indices = np.where(include_mask)[0]
        n = len(included_indices)
        if n < 3:
            logger.warning("Warning: Not enough included points for morphology + mollification.")
            return np.full_like(y, np.nan)

        y_work = y[included_indices]

        try:
            window = 3
            window_history = []
            opening_history = []
            window_size = None
            for _ in range(300):
                if window > n:
                    break
                eroded = grey_erosion(y_work, size=window, mode='nearest')
                opening = grey_dilation(eroded, size=window, mode='nearest')
                window_history.append(window)
                opening_history.append(opening)
                if len(opening_history) >= 3:
                    a, b, c = opening_history[-3:]
                    if np.array_equal(a, b) and np.array_equal(b, c):
                        window_size = window_history[-3]
                        break
                window += 2

            if window_size is None:
                # Same safety fallback as calculate_morphological_baseline
                # and calculate_mpls_baseline.
                window_size = window_history[-1]

            half_window = (window_size - 1) // 2
            if half_window == 0:
                kernel = np.ones(1)
            else:
                kx = (np.arange(2 * half_window + 1) - half_window) / half_window
                kernel = np.zeros_like(kx)
                interior = np.abs(kx) < 1
                kernel[interior] = np.exp(-1.0 / (1.0 - kx[interior] ** 2))
                kernel_sum = kernel.sum()
                if kernel_sum > 0:
                    kernel = kernel / kernel_sum

            # Edge padding: linear extrapolation from each end's own
            # local trend, one window's worth of points on each side.
            fit_pts = min(window_size, n)
            left_x = np.arange(fit_pts)
            left_coef = np.polyfit(left_x, y_work[:fit_pts], 1)
            pad_left = np.polyval(left_coef, np.arange(-window_size, 0))
            right_x = np.arange(fit_pts)
            right_coef = np.polyfit(right_x, y_work[-fit_pts:], 1)
            pad_right = np.polyval(right_coef, np.arange(fit_pts, fit_pts + window_size))
            padded_y = np.concatenate([pad_left, y_work, pad_right])

            baseline = padded_y.copy()
            for _ in range(itermax):
                baseline_old = baseline
                eroded = grey_erosion(baseline, size=window_size, mode='nearest')
                opening = grey_dilation(eroded, size=window_size, mode='nearest')
                dilated = grey_dilation(baseline, size=window_size, mode='nearest')
                closing = grey_erosion(dilated, size=window_size, mode='nearest')
                candidate = np.minimum(padded_y, 0.5 * (closing + opening))

                conv_pad = int(np.ceil(min(len(candidate), len(kernel)) / 2))
                reflected = np.pad(candidate, conv_pad, mode='reflect')
                convolved = np.convolve(reflected, kernel, mode='same')
                baseline = convolved[conv_pad:-conv_pad] if conv_pad > 0 else convolved

                denom = np.linalg.norm(baseline_old)
                calc_diff = np.linalg.norm(baseline - baseline_old) / denom if denom > 0 else 0.0
                if calc_diff < tol:
                    break

            z_included = baseline[window_size:window_size + n]
        except Exception as e:
            logger.error(f"Warning: Error during morphology + mollification fitting: {e}")
            return np.full_like(y, np.nan)

        if n == L:
            return z_included

        return np.interp(np.arange(L), included_indices, z_included)

    def _pspline_fit(self, x, y, w, lam, num_knots=100, spline_degree=3, diff_order=2):
        """
        Weighted penalized B-spline (P-spline) fit -- Eilers & Marx,
        1996's "smoothing with B-splines and penalties": a fixed cubic
        B-spline basis over evenly-spaced knots spanning x's own range,
        fit by weighted least squares with a difference penalty of
        order diff_order on the spline's own coefficients (not on the
        data grid itself, unlike _whittaker_smooth's penalty above --
        num_knots basis functions regardless of how many data points
        there are is the whole point of a P-spline, with lam alone
        controlling smoothness rather than knot count). Used by
        calculate_mpspline_baseline for both of its two spline fits.

        x, y, w : 1-D arrays, same length. w is the per-point weight
        (0 excludes a point from the fit without removing it from the
        basis's domain).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        x_min, x_max = x[0], x[-1]
        dx = (x_max - x_min) / (num_knots - 1)
        inner_knots = np.linspace(x_min, x_max, num_knots)
        knots = np.concatenate((
            np.linspace(x_min - spline_degree * dx, x_min - dx, spline_degree),
            inner_knots,
            np.linspace(x_max + dx, x_max + spline_degree * dx, spline_degree),
        ))

        basis = BSpline.design_matrix(x, knots, spline_degree, extrapolate=True)
        basis = basis.toarray() if hasattr(basis, 'toarray') else np.asarray(basis)
        n_bases = basis.shape[1]

        # Difference penalty on the spline coefficients themselves
        # (Eilers & Marx's P-spline penalty), not on y.
        D = np.eye(n_bases)
        for _ in range(diff_order):
            D = np.diff(D, axis=0)
        penalty = lam * (D.T @ D)

        BtWB = basis.T @ (basis * w[:, None])
        BtWy = basis.T @ (w * y)
        coef = np.linalg.solve(BtWB + penalty, BtWy)
        return basis @ coef

    def calculate_mpspline_baseline(self, y, lam=1e4, p=0.0, num_knots=None,
                                     spline_degree=3, diff_order=2,
                                     itermax=300, exclude_indices=None):
        """
        Calculates a baseline using mpspline (morphology-based penalized
        spline), ignoring specified regions the same way
        calculate_morphological_baseline and calculate_mpls_baseline do.

        mpspline's overall shape mirrors mpls exactly: morphology finds
        a handful of trustworthy anchor points, then a single
        non-iterative weighted least-squares solve is fit through them
        -- no reweighting loop at all. The fit itself is a cubic
        penalized spline (a fixed B-spline basis regularized by a
        difference penalty on its own coefficients, see _pspline_fit)
        rather than mpls's direct Whittaker smoother (a penalty on the
        data grid itself, one coefficient per data point).

        num_knots defaults to None, which resolves to min(n // 2, 2000)
        (n = the number of included points) rather than a single fixed
        constant. pybaselines' own default -- a flat 100 knots no
        matter how large n is -- was tried first here and measured
        against synthetic spectra with tall, narrow peaks (a few
        samples wide, the common case for real Raman peaks sampled at
        typical resolutions): with knots that sparse, stage 1's
        near-unpenalized spline (see lam_smooth below) rings badly
        around a peak it's forced through, overestimating the
        baseline by double digits across a window many times wider
        than the peak itself -- exactly the failure mode pybaselines'
        own source code flags in a comment on that line ("this
        overestimates the data when there is a lot of noise, leading
        to an overestimated baseline"). Doubling the knot count roughly
        halves that error, and by n // 2 it becomes negligible (see the
        test suite), so that's the default; it's capped at 2000 so a
        very large spectrum still solves a bounded dense linear system
        rather than one that grows without limit. A caller who wants
        the literal pybaselines default, or any other fixed count, can
        still pass num_knots explicitly.

        Two stages, both sharing the same P-spline machinery and only
        differing in weights/lambda -- this follows the reference's own
        two-stage structure and the cross-checked open-source
        implementation's weighting scheme for each stage:

        1. Denoise: fit the spline to y, trusting only points a narrow
           (fixed 3-point) morphological closing leaves untouched
           (weight 1; everywhere else weight 0), at a small fixed
           smoothing parameter lam_smooth (see below). This produces a
           denoised curve g -- the reference's own shot-noise-reduction
           stage.
        2. Baseline: reuse calculate_morphological_baseline's own
           window-growth loop, but grown from g rather than y (g is
           already denoised), to find the optimal structuring-element
           window; build the same "opening corrected toward the
           average of its own erosion and dilation" curve that
           calculate_morphological_baseline's refinement step and
           calculate_mpls_baseline's reference both use, and mark every
           point where g exactly matches that curve as an anchor
           (weight 1-p; everywhere else weight p, default p=0.0, same
           convention as mpls). Fit the spline again, through g with
           those weights, at the user-facing lam -- this second fit is
           the returned baseline. Exact equality is safe here (not an
           isclose tolerance) because every value being compared came
           from a pure erosion/dilation selection of g's own samples,
           never from arithmetic that could round differently -- the
           same reasoning calculate_mpls_baseline's boundary detection
           relies on.

        lam_smooth (stage 1's smoothing parameter) is fixed internally
        at 1e-2 rather than exposed as a third slider: the reference
        paper uses a single fixed lambda throughout and explicitly
        designs the method to need no user-tunable parameters at all
        beyond the anchor weight p that mpls's UI convention already
        covers here, so mpspline's dialog page stays to the same two
        sliders as mpls (Smoothness (lambda) and Non-Anchor Weight
        (p)) rather than adding a rarely-meaningful third one. 1e-2
        matches the default used by the open-source implementation
        this was checked against.

        A perfectly flat or monotonic g (no point where the opening
        curve exactly matches g) hits the same degeneracy
        calculate_mpls_baseline's docstring describes for its own
        anchor detection -- fixed the same way, by treating every
        point as an anchor when none are found.

        References: (1) J. J. Gonzalez-Vidal, R. Perez-Pueyo, and M. J.
        Soneira, "Automatic morphology-based cubic p-spline fitting
        methodology for smoothing and baseline-removal of Raman
        spectra." Journal of Raman Spectroscopy 48(6), 878-883 (2017)
        -- the two-stage morphology + cubic p-spline idea itself. (2)
        R. Perez-Pueyo, M. J. Soneira, and S. Ruiz-Moreno,
        "Morphology-based automated baseline removal for Raman spectra
        of artistic pigments." Applied Spectroscopy 64(6), 595-600
        (2010) -- the opening-corrected-toward-its-own-average
        refinement used in stage 2, the same reference
        calculate_morphological_baseline and calculate_mpls_baseline
        already cite for the same refinement.
        """
        y = np.asarray(y, dtype=float)
        L = len(y)

        include_mask = ~exclude_indices if exclude_indices is not None else np.ones(L, dtype=bool)
        included_indices = np.where(include_mask)[0]
        n = len(included_indices)
        if n < max(4, spline_degree + 1):
            logger.warning("Warning: Not enough included points for mpspline.")
            return np.full_like(y, np.nan)

        if num_knots is None:
            # See the docstring above -- a flat 100 rings badly on tall,
            # narrow peaks; scale with n instead, capped for performance.
            num_knots = min(max(n // 2, spline_degree + 1), 2000)

        y_work = y[included_indices]
        x_work = np.arange(n, dtype=float)
        lam_smooth = 1e-2

        try:
            # Stage 1: denoise via a spline trusted only where a narrow
            # closing leaves y untouched.
            closed = grey_erosion(grey_dilation(y_work, size=3, mode='nearest'), size=3, mode='nearest')
            stage1_weights = np.where(y_work == closed, 1.0, 0.0)
            if stage1_weights.sum() < spline_degree + 1:
                # Degenerate case fallback (see docstring) -- trust every point.
                stage1_weights = np.ones(n)
            g = self._pspline_fit(x_work, y_work, stage1_weights, lam_smooth,
                                   num_knots=num_knots, spline_degree=spline_degree,
                                   diff_order=diff_order)

            # Stage 2: grow the optimal structuring-element window from
            # g (see calculate_morphological_baseline for the loop
            # itself).
            window = 3
            window_history = []
            opening_history = []
            optimal_window = None
            optimal_opening = None
            for _ in range(itermax):
                if window > n:
                    break
                eroded = grey_erosion(g, size=window, mode='nearest')
                opening = grey_dilation(eroded, size=window, mode='nearest')
                window_history.append(window)
                opening_history.append(opening)
                if len(opening_history) >= 3:
                    a, b, c = opening_history[-3:]
                    if np.array_equal(a, b) and np.array_equal(b, c):
                        optimal_window = window_history[-3]
                        optimal_opening = a
                        break
                window += 2
            if optimal_opening is None:
                optimal_window = window_history[-1]
                optimal_opening = opening_history[-1]

            d_o = grey_dilation(optimal_opening, size=optimal_window, mode='nearest')
            e_o = grey_erosion(optimal_opening, size=optimal_window, mode='nearest')
            avg_opening = 0.5 * (d_o + e_o)
            optimal_curve = np.minimum(optimal_opening, avg_opening)

            anchor_mask = (g == optimal_curve)
            if anchor_mask.sum() < spline_degree + 1:
                stage2_weights = np.full(n, 1.0 - p)
            else:
                stage2_weights = np.where(anchor_mask, 1.0 - p, p)

            baseline_fit = self._pspline_fit(x_work, g, stage2_weights, lam,
                                              num_knots=num_knots, spline_degree=spline_degree,
                                              diff_order=diff_order)
        except Exception as e:
            logger.error(f"Warning: Error during mpspline fitting: {e}")
            return np.full_like(y, np.nan)

        if n == L:
            return baseline_fit
        return np.interp(np.arange(L), included_indices, baseline_fit)

    def calculate_jbcd_baseline(self, y, alpha=0.1, beta=10.0, itermax=300,
                                 exclude_indices=None):
        """
        Calculates a baseline using jbcd (joint baseline-correction and
        denoising), ignoring specified regions the same way
        calculate_morphological_baseline does -- exclusion is handled
        identically here since this method starts from that same
        morphological opening step.

        Unlike every other hybrid here (mpls, mpspline), which use
        morphology once to pick a handful of anchor points and then
        solve a single weighted system through them, jbcd never singles
        out individual anchor points at all. Instead it solves a single
        joint energy function for a *smooth, denoised spectrum* f and a
        *smooth baseline* b together, minimizing

            E(f,b) = (1/2)||f+b-g||^2 + alpha*||b-Og||^2
                     + beta_t*||D1 b||^2 + gamma_t*||D1 f||^2

        where g is the raw spectrum, Og is the morphological opening of
        g (the same auto-grown-window opening
        calculate_morphological_baseline uses, but *without* that
        method's own erosion/dilation-averaged refinement step -- the
        reference's own Eq. 5 defines Og as the plain opening,
        erosion-then-dilation, nothing more), and D1 is the first-
        difference operator (D1 x)_i = x_{i+1}-x_i, so ||D1 x||^2 is a
        roughness/Tikhonov penalty on x's own slope (not curvature, the
        way ALS's second-difference D penalizes -- a real difference
        from every Whittaker-family method in this class). The first
        term keeps f+b a faithful reconstruction of g; the second pulls
        b toward the morphology-based guide Og (weight alpha, fixed
        throughout); the third and fourth smooth b and f respectively,
        at their own weights beta_t and gamma_t, which change every
        iteration (see below) rather than staying fixed like every
        other algorithm's lambda.

        Solved by alternating minimization (the reference's own
        two-step scheme): fix b, solve the resulting linear system for
        f; fix that f, solve the resulting linear system for b; repeat
        until both stop changing appreciably. Each half-step is an
        ordinary weighted Tikhonov/Whittaker-style solve --

            Step f: (I + 2*gamma_t*D1^T D1) f = (g-b)
            Step b: [(1+2*alpha)*I + 2*beta_t*D1^T D1] b
                        = (g-f) + 2*alpha*Og

        -- so both are solved directly via the existing
        _whittaker_smooth helper (an exact sparse linear solve) rather
        than the reference's own conjugate-gradient iteration: the two
        are mathematically equivalent at convergence (both minimize the
        same convex quadratic), and a direct solve is both simpler and
        exact rather than approximate, the same substitution this
        codebase already makes for the Whittaker family generally
        (ALS's own iterative reweighting solves each step exactly via
        spsolve, not by hand-rolled gradient descent either).

        beta_t and gamma_t are annealed every iteration exactly as the
        reference specifies -- beta_t *= 1.2, gamma_t /= 1.1, starting
        from small/large internal initial values respectively -- which
        the reference describes as shifting weight from denoising
        toward fidelity as the fit settles. One real numerical issue
        found during testing, not in the reference: run long enough
        (compared to this codebase's own synthetic test fixture, tens
        of iterations more than the reference's own reported ~75-
        iteration convergence on their test spectra), beta_t's
        unbounded exponential growth eventually swamps the +2*alpha*I
        term in the b-step's matrix to the point of floating-point
        breakdown (SciPy warns the matrix is "exactly singular"),
        collapsing b to a near-constant flat line regardless of alpha.
        Fixed by capping beta_t's growth at the user-facing `beta`
        value -- not in the reference, which doesn't anneal long enough
        on its own examples to hit this -- rather than letting it grow
        without bound.

        Testing also found that the initial values beta_t and gamma_t
        anneal *from*, and the exact 1.2/1.1 ratios themselves, only
        change how many iterations convergence takes -- not the
        converged baseline itself (confirmed directly: varying either
        initial value by eight orders of magnitude changed the
        converged b by no more than ~1e-4). Only alpha and the beta
        ceiling actually change the returned baseline, so those are the
        only two exposed as dialog sliders -- not three, despite the
        reference nominally having three regularization parameters
        (alpha, beta, gamma) -- with gamma's own initial value, decay
        ratio, and floor, and beta's initial value and growth ratio,
        all fixed internally instead (same reasoning as mpspline's
        internal-only lam_smooth: exposing a parameter the fit doesn't
        actually depend on would just mislead, not help).

        A perfectly flat spectrum has no internal structure for D1 to
        penalize at all (D1's null space is exactly the constant
        vector), so it's recovered essentially exactly -- verified
        numerically, no special-case fallback needed here, the same
        situation calculate_mollification_baseline's own docstring
        describes for the same reason.

        Reference: H. Liu, Z. Zhang, S. Liu, L. Yan, T. Liu, and T.
        Zhang, "Joint Baseline-Correction and Denoising for Raman
        Spectra." Applied Spectroscopy 69(9), 1013-1022 (2015). DOI:
        10.1366/14-07760.
        """
        y = np.asarray(y, dtype=float)
        L = len(y)

        include_mask = ~exclude_indices if exclude_indices is not None else np.ones(L, dtype=bool)
        included_indices = np.where(include_mask)[0]
        n = len(included_indices)
        if n < 3:
            logger.warning("Warning: Not enough included points for jbcd.")
            return np.full_like(y, np.nan)

        y_work = y[included_indices]

        # Internal-only constants -- see docstring for why these three
        # (plus the growth/decay ratios themselves) aren't exposed as
        # sliders. gamma_min is this implementation's own defensive
        # floor (not in the reference), stopping gamma_t underflowing
        # to exactly zero over many iterations.
        gamma_init = 10.0
        beta_init = 1e-6
        beta_growth = 1.2
        gamma_decay = 1.1
        gamma_min = 1e-3
        tol = 1e-6

        try:
            # Og: the plain morphological opening (erosion then
            # dilation), growing the structuring-element window exactly
            # as calculate_morphological_baseline does -- but stopping
            # there, without that method's own extra refinement step
            # (see docstring).
            window = 3
            window_history = []
            opening_history = []
            optimal_opening = None
            for _ in range(itermax):
                if window > n:
                    break
                eroded = grey_erosion(y_work, size=window, mode='nearest')
                opening = grey_dilation(eroded, size=window, mode='nearest')
                window_history.append(window)
                opening_history.append(opening)
                if len(opening_history) >= 3:
                    a, b_hist, c = opening_history[-3:]
                    if np.array_equal(a, b_hist) and np.array_equal(b_hist, c):
                        optimal_opening = a
                        break
                window += 2
            if optimal_opening is None:
                optimal_opening = opening_history[-1]
            Og = optimal_opening

            f = y_work.copy()
            b = Og.copy()
            gamma_t = gamma_init
            beta_t = beta_init
            ones = np.ones(n)
            converged_count = 0
            for _ in range(itermax):
                f_prev, b_prev = f, b

                # Step f (Eq. 11 of the reference).
                f = self._whittaker_smooth(y_work - b, ones, 2 * gamma_t, differences=1)
                gamma_t = max(gamma_t / gamma_decay, gamma_min)

                # Step b (Eq. 13 of the reference).
                combined_target = ((y_work - f) + 2 * alpha * Og) / (1 + 2 * alpha)
                b = self._whittaker_smooth(
                    combined_target, np.full(n, 1 + 2 * alpha), 2 * beta_t, differences=1)
                beta_t = min(beta_t * beta_growth, beta)

                denom_f = np.linalg.norm(f_prev)
                denom_b = np.linalg.norm(b_prev)
                rel_f = np.linalg.norm(f - f_prev) / denom_f if denom_f > 0 else np.linalg.norm(f - f_prev)
                rel_b = np.linalg.norm(b - b_prev) / denom_b if denom_b > 0 else np.linalg.norm(b - b_prev)
                # "More than two consecutive iterations" below both
                # thresholds, per the reference's own Algorithm 1.
                if rel_f < tol and rel_b < tol:
                    converged_count += 1
                    if converged_count > 2:
                        break
                else:
                    converged_count = 0
        except Exception as e:
            logger.error(f"Warning: Error during jbcd fitting: {e}")
            return np.full_like(y, np.nan)

        if n == L:
            return b
        return np.interp(np.arange(L), included_indices, b)

    # ------------------------------------------------------------------ #
    # Computing the baselines (serial or parallel)                        #
    # ------------------------------------------------------------------ #

    def _baseline_for_spectrum(self, algorithm, x_scale, y_scale, cfg):
        """The baseline of ONE spectrum. The single place that turns the
        settings into an algorithm call: used by the serial path and by
        the worker processes alike, which is what guarantees identical
        results in every processing mode."""
        region_mask = np.zeros_like(x_scale, dtype=bool)
        for start, end in cfg['fitting_ranges']:
            low, high = min(start, end), max(start, end)
            region_mask |= (x_scale >= low) & (x_scale <= high)
        # If "Invert" is checked, we exclude everything OUTSIDE the selected regions.
        exclude_mask = ~region_mask if cfg['invert_regions'] else region_mask
        lam, p, eta, n_iter = cfg['lam'], cfg['p'], cfg['eta'], cfg['n_iter']

        if algorithm == 'airpls':
            return self.calculate_airpls_baseline(
                y_scale, lam=lam, porder=1, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'arpls':
            return self.calculate_arpls_baseline(
                y_scale, lam=lam, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'iarpls':
            return self.calculate_iarpls_baseline(
                y_scale, lam=lam, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'aspls':
            return self.calculate_aspls_baseline(
                y_scale, lam=lam, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'drpls':
            return self.calculate_drpls_baseline(
                y_scale, lam=lam, eta=eta, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'psalsa':
            return self.calculate_psalsa_baseline(
                y_scale, lam=lam, p=p, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'imodpoly':
            return self.calculate_imodpoly_baseline(
                x_scale, y_scale, poly_order=cfg['poly_order'], itermax=n_iter,
                exclude_indices=exclude_mask)
        if algorithm == 'morphological':
            return self.calculate_morphological_baseline(
                y_scale, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'mpls':
            return self.calculate_mpls_baseline(
                y_scale, lam=lam, p=p, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'mollification':
            return self.calculate_mollification_baseline(
                y_scale, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'mpspline':
            return self.calculate_mpspline_baseline(
                y_scale, lam=lam, p=p, itermax=n_iter, exclude_indices=exclude_mask)
        if algorithm == 'jbcd':
            return self.calculate_jbcd_baseline(
                y_scale, alpha=cfg['alpha'], beta=cfg['beta'], itermax=n_iter,
                exclude_indices=exclude_mask)
        return self.calculate_als_baseline(
            y_scale, lam=lam, p=p, niter=n_iter, exclude_indices=exclude_mask)

    def _report_progress(self, force=False):
        """Tell the progress callable how far we are -- but not more than
        about 20 times a second (a call refreshes the window, which costs
        more than a fast spectrum). Often enough that Windows never sees
        the window as "not responding" (which makes it flicker)."""
        if self._progress_fn is None:
            return
        now = time.perf_counter()
        if not force and now - self._progress_last < _PROGRESS_MIN_INTERVAL:
            return
        self._progress_last = now
        self._progress_fn(self._progress_done, self._progress_total)

    def _compute_serial(self, spectra, indices, algorithm, cfg, baselines, progress_callback):
        for i in indices:
            notify_progress(progress_callback, i)
            spectrum = spectra[i]
            baselines[i] = self._baseline_for_spectrum(
                algorithm, spectrum['x_scale'], spectrum['y_scale'].copy(), cfg)
            self._progress_done += 1
            self._report_progress()

    def _compute_all_baselines(self, spectra, algorithm, cfg, mode, max_workers,
                               progress_callback, status_callback, progress=None):
        """Baseline (array, or None for a failed fit) of every spectrum.
        Fills self.last_run_info; see apply_correction for the modes."""
        n = len(spectra)
        started = time.perf_counter()
        if mode not in ('auto', 'serial', 'parallel'):
            mode = 'auto'
        info = {'requested_mode': mode, 'mode': 'serial', 'workers': 1,
                'n_spectra': n, 'seconds': 0.0, 'fallback_reason': None, 'note': None}
        self.last_run_info = info
        baselines = [None] * n
        remaining = list(range(n))
        self._progress_fn = progress
        self._progress_total = n
        self._progress_done = 0
        self._progress_last = 0.0

        workers = resolve_worker_count(max_workers) if mode != 'serial' else 1
        if mode != 'serial' and (workers < 2 or n < 2):
            info['note'] = (f'only one worker is available ({describe_worker_limits()}), '
                            f'so parallel processing was not used' if workers < 2
                            else 'there is only one spectrum')
            mode = 'serial'

        if mode == 'auto':
            # Time the first few spectra here, then decide with the real
            # speed of this machine and method whether starting worker
            # processes (a few seconds on Windows) is worth it.
            calibration = remaining[:_AUTO_CALIBRATION_SPECTRA]
            t0 = time.perf_counter()
            self._compute_serial(spectra, calibration, algorithm, cfg, baselines,
                                 progress_callback)
            per_spectrum = (time.perf_counter() - t0) / len(calibration)
            remaining = remaining[len(calibration):]
            serial_estimate = per_spectrum * len(remaining)
            parallel_estimate = _POOL_STARTUP_SECONDS + serial_estimate / workers
            if (serial_estimate >= _AUTO_MIN_SERIAL_SECONDS
                    and parallel_estimate <= 0.7 * serial_estimate):
                mode = 'parallel'
            else:
                info['note'] = (f'the job is short (about {serial_estimate:.1f} s '
                                f'for the rest), so parallel workers would not pay off')

        if mode == 'parallel' and remaining:
            try:
                if status_callback is not None:
                    status_callback("Starting parallel workers\u2026")
                self._compute_parallel(spectra, remaining, algorithm, cfg, baselines,
                                       workers, progress_callback)
                if status_callback is not None:
                    status_callback("Finishing\u2026")
                info['mode'] = 'parallel'
                info['workers'] = workers
                remaining = []
            except OperationCancelled:
                raise                  # the user cancelled: no serial redo
            except Exception as exc:
                # Any pool problem (cannot start, killed for lack of
                # memory, ...) -- or an error in the algorithm itself,
                # which then raises again below, just as in serial mode.
                logger.warning(
                    "Parallel baseline correction failed (%r); "
                    "redoing it serially.", exc)
                info['fallback_reason'] = f'{type(exc).__name__}: {exc}'
                for i in remaining:
                    baselines[i] = None
                self._progress_done = n - len(remaining)   # count again from the redo's start

        if remaining:
            self._compute_serial(spectra, remaining, algorithm, cfg, baselines,
                                 progress_callback)
        info['seconds'] = time.perf_counter() - started
        self._report_progress(force=True)
        return baselines

    def _compute_parallel(self, spectra, indices, algorithm, cfg, baselines,
                          workers, progress_callback):
        # Several chunks per worker: keeps all workers busy when some
        # spectra take longer, and gives the progress callback regular
        # chances to run. Only the x/y arrays travel to the workers (not
        # whole spectrum dicts with their metadata), and a common x axis
        # is sent once per chunk.
        n_chunks = min(len(indices), workers * 4)
        chunks = [list(part) for part in np.array_split(np.array(indices), n_chunks)]
        payloads = []
        for chunk in chunks:
            xs = [np.asarray(spectra[i]['x_scale']) for i in chunk]
            ys = [np.asarray(spectra[i]['y_scale']) for i in chunk]
            x0 = xs[0]
            shared = all(len(x) == len(x0) and np.array_equal(x, x0) for x in xs)
            payloads.append((algorithm, cfg, x0 if shared else None,
                             None if shared else xs, ys))
        def tick():
            if progress_callback is not None:
                progress_callback()
            self._report_progress(force=True)

        def chunk_done(k):
            self._progress_done += len(chunks[k])

        results = run_in_process_pool(
            _baseline_chunk_worker, payloads, workers, tick, chunk_done)
        for chunk, chunk_baselines in zip(chunks, results):
            for i, baseline in zip(chunk, chunk_baselines):
                baselines[i] = baseline

    def run_summary(self):
        """One sentence about how the last apply_correction() call was run
        (empty if there was none) -- shown to the user so serial and
        parallel runs can be compared."""
        info = getattr(self, 'last_run_info', None)
        if not info:
            return ''
        n = info['n_spectra']
        noun = 'spectrum' if n == 1 else 'spectra'
        how = (f"parallel, {info['workers']} workers" if info['mode'] == 'parallel'
               else 'serial')
        seconds = info['seconds']
        took = f"{seconds:.2f}" if seconds < 10 else f"{seconds:.1f}"
        text = f"Computed {n} {noun} in {took} s ({how})."
        if info['note'] and n > 1:
            text += f" Ran serially: {info['note']}."
        if info['fallback_reason']:
            text += (f" Parallel processing failed and the job was redone serially "
                     f"({info['fallback_reason']}).")
        return text

    def apply_correction(self, spectra: list, params: dict, progress_callback=None,
                         status_callback=None, progress=None) -> list:
        """
        Applies automated baseline correction (see params['algorithm']
        below) to a list of spectra.

        Each returned spectrum's metadata['correction_history'] gets a new
        'Automated Baseline' entry that includes a 'success' flag.
        Previously this metadata was written unconditionally, claiming a
        specific ALS correction (with its exact lambda/p/iteration values)
        had been applied even when the baseline computation failed and
        y_scale was left completely unchanged — e.g. because the selected
        fitting regions excluded every point, leaving nothing to fit or
        interpolate through. That made the metadata actively misleading:
        it recorded a correction that never actually happened, with no
        way to tell afterward (from the spectrum's own record) that it
        hadn't. failed_labels is also attached to the manager
        (self.failed_labels) after each call so the caller can surface a
        warning — the manager only logs failures, which is invisible in
        the running app.

        progress_callback : optional callable, invoked every 50 spectra
            during the loop below — see SNIPBaselineManager.apply_correction
            for the full reasoning; same hook/contract. None (the
            default) — no change from before.

        params['algorithm'] selects the fitting algorithm: 'als' (the
        default — unchanged behavior from before airPLS existed),
        'airpls', 'arpls', 'iarpls', 'aspls', 'drpls', 'psalsa',
        'imodpoly', 'morphological', 'mpls', 'mollification',
        'mpspline', or 'jbcd'.

        params['processing_mode'] chooses how the baselines are computed
        (the result is identical in every mode, only the speed differs):
        'auto' (the default; also used for settings saved before this
        option existed) times the first few spectra and uses parallel
        worker processes only when the rest of the job is long enough to
        pay for starting them; 'serial' computes everything one spectrum
        after another in this process; 'parallel' always uses worker
        processes (when at least two workers and two spectra are
        available). params['max_workers'] (0/absent = automatic, limited
        by CPU cores and free memory) sets the number of workers.
        After every call self.last_run_info says what was actually done
        and run_summary() turns it into a sentence for the user.

        status_callback : optional callable(str) that receives short
            status texts such as "Starting parallel workers…" (a caller
            with a progress dialog can show them as its label).

        progress : optional callable(done, total), called after spectra
            are finished (at most about 20 times a second, and about ten
            times a second while parallel workers are busy) -- for a
            progress bar and for keeping the window alive. It may raise
            OperationCancelled (e.g. the user pressed Cancel): the call
            then raises it too, stops at once and returns nothing, so the
            caller can leave the spectra unchanged.
        """
        algorithm = params.get('algorithm', 'als')
        is_airpls = (algorithm == 'airpls')
        is_arpls = (algorithm == 'arpls')
        is_iarpls = (algorithm == 'iarpls')
        is_aspls = (algorithm == 'aspls')
        is_drpls = (algorithm == 'drpls')
        is_psalsa = (algorithm == 'psalsa')
        is_imodpoly = (algorithm == 'imodpoly')
        is_morph = (algorithm == 'morphological')
        is_mpls = (algorithm == 'mpls')
        is_mollification = (algorithm == 'mollification')
        is_mpspline = (algorithm == 'mpspline')
        is_jbcd = (algorithm == 'jbcd')
        if is_airpls:
            default_lam, default_n_iter = 1e4, 20
        elif is_arpls:
            default_lam, default_n_iter = 1e5, 50
        elif is_iarpls:
            default_lam, default_n_iter = 1e5, 100  # same lambda scale as arPLS; itermax higher since iarpls's weighting keeps sharpening up to iteration 100
        elif is_aspls:
            default_lam, default_n_iter = 1e6, 100  # same lambda scale as ALS -- the alpha-scaled penalty (not a bigger lambda) is what does asPLS's adaptive work
        elif is_drpls:
            default_lam, default_n_iter = 1e5, 50  # same lambda scale as arPLS -- the extra first-order penalty term has no lambda of its own
        elif is_psalsa:
            default_lam, default_n_iter = 1e6, 50  # same lambda scale as ALS -- psalsa reuses ALS's second-order penalty, just a different weight formula
        elif is_imodpoly:
            default_lam, default_n_iter = 1e6, 100  # lambda unused by I-ModPoly; n_iter is its itermax safety cap
        elif is_morph:
            default_lam, default_n_iter = 1e6, 300  # lambda unused; n_iter is the structuring-element growth-step cap
        elif is_mpls:
            default_lam, default_n_iter = 1e6, 300  # same lambda scale as ALS (single weighted solve, not iterative); n_iter is the shared structuring-element growth-step cap
        elif is_mollification:
            default_lam, default_n_iter = 1e6, 200  # lambda unused -- no system of equations to solve at all; n_iter is the convolution-loop's own itermax (distinct from the structuring-element growth cap, fixed internally at 300)
        elif is_mpspline:
            default_lam, default_n_iter = 1e4, 300  # a different lambda scale than every other method here -- this one penalizes ~100 spline coefficients directly, not the data grid, so it isn't comparable to ALS/mpls's 1e6; matches the open-source implementation's own default. n_iter is the shared structuring-element growth-step cap
        elif is_jbcd:
            default_lam, default_n_iter = 1e6, 300  # lambda unused -- jbcd has its own alpha/beta regularization pair instead; n_iter is the shared alternating-minimization itermax (also bounds the structuring-element growth loop for its own Og step)
        else:
            default_lam, default_n_iter = 1e6, 10
        lam = params.get('lambda', default_lam)
        # psalsa's exponential peak-decay weighting lets p sit much
        # higher than ALS's own default without under-suppressing real
        # peaks -- 0.5 matches the value used in the reference/the
        # open-source implementation this was checked against.
        # mpls's p has a different meaning and scale than ALS/psalsa's:
        # it's the weight given to every NON-anchor point (anchor points
        # always get 1-p), so 0.0 -- trusting the morphology-identified
        # anchors completely and ignoring everything else -- is both the
        # paper's own default and the open-source implementation's.
        # mpspline's p is the exact same convention (mpspline's anchor
        # points feed the same 1-p/p weighting into its own spline fit).
        default_p = 0.0 if (is_mpls or is_mpspline) else (0.5 if is_psalsa else 0.01)
        p = params.get('p', default_p)
        # drPLS's own second tunable parameter -- how much the
        # second-order penalty relaxes under high-weight (peak)
        # regions. 0.5 matches the default used by the open-source
        # implementation this was checked against.
        eta = params.get('eta', 0.5)
        n_iter = params.get('n_iter', default_n_iter)
        poly_order = params.get('poly_order', 5)
        # jbcd's own two exposed regularization weights -- see
        # calculate_jbcd_baseline's docstring for why only these two
        # (of the reference's nominal three) are user-facing.
        alpha = params.get('alpha', 0.1)
        beta = params.get('beta', 10.0)
        fitting_ranges = params.get('fitting_ranges', [])
        invert_regions = params.get('invert_regions', False)

        corrected_spectra = []
        self.failed_labels = []
        algo_label = _ALGORITHM_LABELS.get(algorithm, 'ALS')
        cfg = {
            'lam': lam, 'p': p, 'eta': eta, 'n_iter': n_iter,
            'poly_order': poly_order, 'alpha': alpha, 'beta': beta,
            'fitting_ranges': [tuple(r) for r in fitting_ranges],
            'invert_regions': bool(invert_regions),
        }
        # All baselines first (serially or in worker processes -- the very
        # same function computes each one), then the cheap bookkeeping
        # below always runs here in this process, identically in every
        # processing mode.
        baselines = self._compute_all_baselines(
            spectra, algorithm, cfg,
            params.get('processing_mode', 'auto'), params.get('max_workers', 0),
            progress_callback, status_callback, progress)
        for i, spectrum in enumerate(spectra):
            corrected_spectrum = {key: (value.copy() if hasattr(value, 'copy') else value)
                                  for key, value in spectrum.items()}

            y_scale = corrected_spectrum['y_scale']
            baseline = baselines[i]

            # Subtract the baseline (only if calculation was successful)
            success = baseline is not None and not np.isnan(baseline).all()
            if success:
                corrected_spectrum['y_scale'] = y_scale - baseline
            else:
                self.failed_labels.append(spectrum.get('label', '?'))
                logger.warning(
                    "Automated baseline correction failed for '%s' — "
                    "spectrum left unchanged (see the warning/error above "
                    "for the specific reason).",
                    spectrum.get('label', '?')
                )
            
            # Store correction info in metadata
            if 'metadata' not in corrected_spectrum:
                corrected_spectrum['metadata'] = {}
            
            entry_fields = {
                'success': success,
                'algorithm': algo_label,
                'iterations': n_iter, 'fitting_ranges': fitting_ranges,
                'inverted_regions': invert_regions,
            }
            # lambda only means anything for the Whittaker-family
            # methods (ALS/airPLS/arPLS); I-ModPoly has poly_order
            # instead. p (asymmetry) only means anything for ALS. Both
            # omitted where they don't apply rather than written as a
            # meaningless value — the per-spectrum detail table already
            # shows a blank cell for any key missing from a given entry.
            if is_imodpoly:
                entry_fields['poly_order'] = poly_order
            elif is_morph or is_mollification:
                pass  # fully parameter-free -- no lambda, p, or poly_order applies
            elif is_jbcd:
                entry_fields['alpha'] = alpha
                entry_fields['beta'] = beta
            else:
                entry_fields['lambda'] = lam
                if not is_airpls and not is_arpls and not is_iarpls and not is_aspls and not is_drpls:
                    entry_fields['p'] = p
                if is_drpls:
                    entry_fields['eta'] = eta
            # Shared, chronologically-ordered history across every
            # operation type that records one (see correction_history.py).
            # This used to ALSO be written as a separate flat
            # metadata['auto_baseline_correction'] key holding the exact
            # same dict — nothing else in the codebase ever read that key
            # (confirmed by search), so it was pure dead weight that just
            # made this one correction show up twice in the metadata
            # viewer dialog (once as its own section, once again inside
            # Correction History). Removed; correction_history alone is
            # the single source of truth now, same as every other
            # operation in this file's family.
            corrected_spectrum['metadata']['correction_history'] = append_correction_history(
                spectrum.get('metadata'), 'Automated Baseline', entry_fields
            )
            corrected_spectra.append(corrected_spectrum)
            
        return corrected_spectra


def _baseline_chunk_worker(payload):
    """Worker-process entry point (must stay a top-level function): the
    baselines of one chunk of spectra, via the very same
    _baseline_for_spectrum() the serial path uses."""
    algorithm, cfg, x_shared, xs, ys = payload
    manager = AutomatedBaselineManager()
    results = []
    for k, y in enumerate(ys):
        x = x_shared if x_shared is not None else xs[k]
        results.append(manager._baseline_for_spectrum(algorithm, x, y.copy(), cfg))
    return results
