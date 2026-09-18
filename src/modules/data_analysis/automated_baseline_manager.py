# src/modules/data_analysis/automated_baseline_manager.py

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.ndimage import grey_erosion, grey_dilation
from src.modules.utils.app_logger import get_logger
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)


class AutomatedBaselineManager:
    """
    Business logic for automated baseline correction. Six algorithms,
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
    All six support region exclusion via params['fitting_ranges'] +
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

    def apply_correction(self, spectra: list, params: dict, progress_callback=None) -> list:
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
        'airpls', 'arpls', 'iarpls', 'imodpoly', or 'morphological'.
        """
        algorithm = params.get('algorithm', 'als')
        is_airpls = (algorithm == 'airpls')
        is_arpls = (algorithm == 'arpls')
        is_iarpls = (algorithm == 'iarpls')
        is_imodpoly = (algorithm == 'imodpoly')
        is_morph = (algorithm == 'morphological')
        if is_airpls:
            default_lam, default_n_iter = 1e4, 20
        elif is_arpls:
            default_lam, default_n_iter = 1e5, 50
        elif is_iarpls:
            default_lam, default_n_iter = 1e5, 100  # same lambda scale as arPLS; itermax higher since iarpls's weighting keeps sharpening up to iteration 100
        elif is_imodpoly:
            default_lam, default_n_iter = 1e6, 100  # lambda unused by I-ModPoly; n_iter is its itermax safety cap
        elif is_morph:
            default_lam, default_n_iter = 1e6, 300  # lambda unused; n_iter is the structuring-element growth-step cap
        else:
            default_lam, default_n_iter = 1e6, 10
        lam = params.get('lambda', default_lam)
        p = params.get('p', 0.01)
        n_iter = params.get('n_iter', default_n_iter)
        poly_order = params.get('poly_order', 5)
        fitting_ranges = params.get('fitting_ranges', [])
        invert_regions = params.get('invert_regions', False)

        corrected_spectra = []
        self.failed_labels = []
        for i, spectrum in enumerate(spectra):
            notify_progress(progress_callback, i)
            corrected_spectrum = {key: (value.copy() if hasattr(value, 'copy') else value)
                                  for key, value in spectrum.items()}

            y_scale = corrected_spectrum['y_scale']
            x_scale = corrected_spectrum['x_scale']

            # Create the region mask from user-defined ranges
            region_mask = np.zeros_like(x_scale, dtype=bool)
            if fitting_ranges:
                for start, end in fitting_ranges:
                    low, high = min(start, end), max(start, end)
                    region_mask |= (x_scale >= low) & (x_scale <= high)
            
            # If "Invert" is checked, we exclude everything OUTSIDE the selected regions.
            exclude_mask = ~region_mask if invert_regions else region_mask

            # Calculate the baseline
            if is_airpls:
                baseline = self.calculate_airpls_baseline(
                    y_scale, lam=lam, porder=1, itermax=n_iter, exclude_indices=exclude_mask)
                algo_label = 'airPLS'
            elif is_arpls:
                baseline = self.calculate_arpls_baseline(
                    y_scale, lam=lam, itermax=n_iter, exclude_indices=exclude_mask)
                algo_label = 'arPLS'
            elif is_iarpls:
                baseline = self.calculate_iarpls_baseline(
                    y_scale, lam=lam, itermax=n_iter, exclude_indices=exclude_mask)
                algo_label = 'iarPLS'
            elif is_imodpoly:
                baseline = self.calculate_imodpoly_baseline(
                    x_scale, y_scale, poly_order=poly_order, itermax=n_iter, exclude_indices=exclude_mask)
                algo_label = 'I-ModPoly'
            elif is_morph:
                baseline = self.calculate_morphological_baseline(
                    y_scale, itermax=n_iter, exclude_indices=exclude_mask)
                algo_label = 'Morphological Opening'
            else:
                baseline = self.calculate_als_baseline(y_scale, lam=lam, p=p, niter=n_iter, exclude_indices=exclude_mask)
                algo_label = 'ALS'
            
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
            elif is_morph:
                pass  # fully parameter-free -- no lambda, p, or poly_order applies
            else:
                entry_fields['lambda'] = lam
                if not is_airpls and not is_arpls and not is_iarpls:
                    entry_fields['p'] = p
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