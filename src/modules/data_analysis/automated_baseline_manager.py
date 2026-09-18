# src/modules/data_analysis/automated_baseline_manager.py

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve
from src.modules.utils.app_logger import get_logger
from src.modules.utils.progress_utils import notify_progress
from src.modules.utils.correction_history import append_correction_history
logger = get_logger(__name__)


class AutomatedBaselineManager:
    """
    Business logic for automated baseline correction. Four algorithms,
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
      - 'imodpoly': Improved Modified Polynomial fit (Zhao, Lui, McLean
        & Zeng, 2007) — fits a single low-order polynomial rather than a
        Whittaker-smoothed curve, with its own iterative peak-rejection
        and a residual-standard-deviation-based stopping rule (see
        calculate_imodpoly_baseline). Its own 'poly_order' parameter
        replaces 'lambda'/'p'; not a member of the Whittaker family
        above.
    All four support region exclusion via params['fitting_ranges'] +
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
        'airpls', 'arpls', or 'imodpoly'.
        """
        algorithm = params.get('algorithm', 'als')
        is_airpls = (algorithm == 'airpls')
        is_arpls = (algorithm == 'arpls')
        is_imodpoly = (algorithm == 'imodpoly')
        if is_airpls:
            default_lam, default_n_iter = 1e4, 20
        elif is_arpls:
            default_lam, default_n_iter = 1e5, 50
        elif is_imodpoly:
            default_lam, default_n_iter = 1e6, 100  # lambda unused by I-ModPoly; n_iter is its itermax safety cap
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
            elif is_imodpoly:
                baseline = self.calculate_imodpoly_baseline(
                    x_scale, y_scale, poly_order=poly_order, itermax=n_iter, exclude_indices=exclude_mask)
                algo_label = 'I-ModPoly'
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
            else:
                entry_fields['lambda'] = lam
                if not is_airpls and not is_arpls:
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