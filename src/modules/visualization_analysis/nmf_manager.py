# src/modules/visualization_analysis/nmf_manager.py
"""
Non-negative Matrix Factorisation (NMF) manager.

Decomposes a spectral matrix X (n_spectra × n_wavelengths) into:
    W  : (n_spectra × n_components)  — scores / abundances per spectrum
    H  : (n_components × n_wavelengths) — components (spectral profiles)

Both W and H are non-negative, so components resemble real spectra and
scores resemble concentrations — physically interpretable for mixtures.
"""

import os
import numpy as np
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match

logger = get_logger(__name__)


class NMFManager:

    def __init__(self):
        self.W            = None   # (n_spectra × n_comp)
        self.H            = None   # (n_comp × n_wl)
        self.x_axis       = None
        self.labels       = []
        self.n_components = None
        self.reconstruction_error = None
        self.lof            = None   # % lack-of-fit, same formula/meaning as MCRALSManager.lof
        self.iterations_used = None
        self.converged      = False
        self.explained_variance   = None   # % of the DATA's own squared norm
                                            # explained by each component
                                            # (see compute()) — doesn't
                                            # necessarily sum to 100%
        self.offset       = 0.0    # constant subtracted before fitting (see compute())
        self.X_nn         = None   # (n_spectra x n_wl) -- the aligned, clipped
                                    # data matrix this fit was run on; kept for
                                    # compute_bootstrap_uncertainty() (see
                                    # MCRALSManager.D for the identical idea)
        self.bootstrap_result = None   # set by compute_bootstrap_uncertainty()
        self.reference_components = []    # component slots anchored to known spectra
        self.references_fixed = False     # whether those slots were held constant
        self.x_range_mismatch_warning = None   # set by compute() if spectra have differing x-ranges
        self.last_error = None     # specific reason if compute() returns False

    def reset(self):
        """Clear all previous results — same purpose as
        ClusterAnalysisManager.reset()/PcaScoresManager.reset(): without
        this, a controller's manager reused across dialog sessions could
        still hold a previous, unrelated selection's W/H when a fresh
        dialog opens, before the first NMF run for the new selection
        finishes."""
        self.__init__()

    def compute(self, spectra: list, n_components: int,
                init: str = 'nndsvda', max_iter: int = 500,
                random_state: int = 42,
                references: dict = None, fix_references: bool = False,
                init_H: np.ndarray = None) -> bool:
        """
        Run NMF on the selected spectra.

        Parameters
        ----------
        spectra      : list of spectrum dicts
        n_components : number of NMF components
        init         : NMF initialisation ('nndsvda', 'random', 'nndsvd').
            Ignored when init_H is given (see below).
        max_iter     : maximum iterations
        random_state : random seed (used only for init='random')
        init_H : optional (n_components, n_wl) array. When given, this
            EXACT array is used as the starting components guess -- 'init'
            and the normal ref_rows/residual seeding logic are all skipped
            entirely, since init_H is trusted to already be a valid,
            converged starting point (typically another NMFManager's own
            self.H from a prior successful compute() call). This is a warm
            start, not a new initial guess: it exists so
            compute_bootstrap_uncertainty() (see
            NMFController.compute_bootstrap_uncertainty) can refit the SAME
            dataset-with-resampled-noise from THIS exact solution, keeping
            every bootstrap replicate in the same solution basin/component
            identity instead of reintroducing rotational ambiguity on every
            resample -- see MCRALSManager.compute()'s identical init_ST for
            the same reasoning, and the Developer Guide's "NMF Bootstrap
            Uncertainty" section for the full method.

            Whenever init_H is given, the fit ALWAYS runs through
            _fit_with_references() (the hand-written multiplicative-update
            loop), even when there are no reference spectra at all --
            scikit-learn's NMF has no supported way to warm-start from an
            arbitrary, externally-chosen H, so a warm-started replicate
            can't go through the same code path a reference-free cold fit
            used. This is safe in the sense that matters here -- it never
            drifts to a DIFFERENT point/rotation than the one it started
            from, because any genuine local minimum of the Frobenius NMF
            objective is *also* a fixed point of the Lee & Seung
            multiplicative-update rule (both search for stationary points
            of the same objective under the same non-negativity
            constraints). It does NOT, however, guarantee the warm fit
            finishes in only a couple of iterations when the reference
            came from scikit-learn's own solver: scikit-learn's default
            convergence tolerance (tol=1e-4, not exposed through this
            method) is measurably looser than the MU loop's own
            convergence check, so a warm start from an sklearn-cold-fitted
            reference will typically keep visibly improving reconstruction
            error for many further iterations, converging toward a nearby,
            NON-rotated, tighter optimum rather than reproducing the
            reference numerically -- confirmed empirically (see
            tests/test_nmf_bootstrap.py::TestInitHWarmStart, both the
            same-algorithm case that DOES stabilize in a couple of
            iterations, and the realistic sklearn-cold-start case that
            doesn't but still stays in the same basin/component identity).

            Also skips the end-of-fit reorder-by-explained-variance step
            below, for the same reason MCRALSManager.compute()'s init_ST
            does -- a warm-started refit should keep the slot order it
            started from, not re-sort itself independently each time.
            Raises no exception on a shape mismatch; returns False with
            self.last_error set instead, consistent with every other
            validation failure in this method.

        Returns True on success.
        """
        if not spectra:
            self.last_error = "No spectra selected."
            return False

        self.last_error = None

        # Hard block: if any spectrum's range doesn't overlap the reference
        # spectrum's range AT ALL (e.g. one set of spectra spans 400-900,
        # another spans 1400-2400), interpolating it onto the reference
        # grid produces values with no relationship to that spectrum's
        # actual data — not a minor artifact, a meaningless result. This is
        # checked before anything else runs, so it fails clearly instead of
        # silently producing nonsense.
        x_ref_check = np.asarray(spectra[0]['x_scale'], dtype=float)
        ref_min, ref_max = x_ref_check.min(), x_ref_check.max()
        for s in spectra[1:]:
            x_check = np.asarray(s['x_scale'], dtype=float)
            s_min, s_max = x_check.min(), x_check.max()
            if s_max < ref_min or s_min > ref_max:
                self.last_error = (
                    f"Spectra have non-overlapping x-axis ranges \u2014 cannot run NMF.\n\n"
                    f"Reference spectrum ('{spectra[0].get('label', '?')}'): "
                    f"{ref_min:.4g} to {ref_max:.4g}\n"
                    f"Spectrum '{s.get('label', '?')}': {s_min:.4g} to {s_max:.4g}\n\n"
                    "These do not overlap at all, so there's no shared x-range "
                    "for NMF to decompose. Please select only spectra that cover "
                    "the same spectral region."
                )
                return False

        try:
            from sklearn.decomposition import NMF
        except ImportError:
            logger.error("NMFManager: scikit-learn is not installed")
            self.last_error = "NMF needs the scikit-learn package, which is not installed."
            return False

        # Build data matrix (n_spectra × n_wl), clip negatives
        # BUG FIX — np.interp() below REQUIRES an ascending x. Given a descending
        # x it does not raise: it silently returns nonsense (we measured 100% of
        # the signal destroyed on a real spectrum). Descending x is not exotic —
        # Raman files are very commonly stored in descending wavenumber order, and
        # a set where some spectra ascend and others descend is enough to trigger
        # it. Nothing upstream guaranteed ascending order: the interlaced importer
        # sorts, but the standard and row-oriented importers deliberately preserve
        # file order.
        #
        # So sort every spectrum by ascending x here, at the point of use. This is
        # a pure reordering — each y stays attached to its own x — so it cannot
        # change any legitimate result; it only removes a way to get a silently
        # wrong one.
        def _ascending(xs, ys):
            xs = np.asarray(xs, dtype=float)
            ys = np.asarray(ys, dtype=float)
            if xs.size > 1 and np.any(np.diff(xs) < 0):
                order = np.argsort(xs, kind='stable')
                return xs[order], ys[order]
            return xs, ys

        spectra = [dict(s) for s in spectra]
        for s in spectra:
            s['x_scale'], s['y_scale'] = _ascending(s['x_scale'], s['y_scale'])

        # --- require identical x-axes, exactly as SVD and PCA already do -------
        #
        # This used to silently RESAMPLE every spectrum onto the first one's grid
        # (np.interp). That is a hidden transformation of the user's data, and it
        # fails in ways nobody can see:
        #
        #   * a different step size is silently re-gridded;
        #   * a spectrum covering a NARROWER range is flat-EXTRAPOLATED across the
        #     gap — invented numbers, then fitted as if they were measurements.
        #
        # The application already has a clear, modular answer to mismatched axes:
        # SVD/PCA refuse and the user harmonises the spectra with the Data Range
        # operation, which does the resampling openly, once, where it can be seen
        # and checked. MCR-ALS and NMF quietly doing their own private version of
        # that was both a duplication and a trap. They now refuse in the same way,
        # with the same kind of message.
        ref_x = np.asarray(spectra[0]['x_scale'], dtype=float)
        ref_label = spectra[0].get('label', '?')
        for s in spectra[1:]:
            sx = np.asarray(s['x_scale'], dtype=float)
            # Same tolerance-aware comparison the GUI guard uses — see
            # spectra_validation.axes_match. An exact == would reject axes that
            # are physically identical but differ in their last bits (e.g. one
            # rebuilt by arithmetic in Data Range); a fixed absolute tolerance
            # cannot suit both a UV/Vis axis in nm and a THz axis in cm-1.
            if not axes_match(ref_x, sx):
                self.last_error = (
                    "Spectra have different x-axes.\n\n"
                    f"First spectrum ('{ref_label}'): {ref_x.size} points "
                    f"({ref_x.min():g} to {ref_x.max():g})\n"
                    f"Spectrum '{s.get('label', '?')}': {sx.size} points "
                    f"({sx.min():g} to {sx.max():g})\n\n"
                    "All spectra must share an identical x-axis. Use the Data Range "
                    "operation to put them on a common axis first."
                )
                logger.error("%s: %s", self.__class__.__name__, self.last_error)
                return False

        x_ref = ref_x
        x_ref_min, x_ref_max = x_ref.min(), x_ref.max()
        # Same tolerance concept as axes_match (spectra_validation.py):
        # scaled to the data's own step size, not a fixed absolute number.
        # A hardcoded 1e-9 here would be TIGHTER than the tolerance
        # axes_match just used to decide these spectra match at all for a
        # coarse-step axis (e.g. step=10000 -> axes_match tolerance=0.01,
        # a hundred thousand times looser than 1e-9) — meaning a pair
        # already confirmed to be "the same axis" could still trip this
        # separate, stricter check and produce a spurious "narrower range,
        # values held flat" warning about spectra that don't actually
        # have a meaningfully different range at all. (Same fix as
        # MCRALSManager.compute — this file and that one share the same
        # x-axis-handling template.)
        if x_ref.size > 1:
            _step = float(np.median(np.abs(np.diff(x_ref))))
            _range_tol = _step * 1e-6 if np.isfinite(_step) and _step > 0 else 1e-9
        else:
            _range_tol = 1e-9
        rows  = []
        mismatched_labels = []
        for s in spectra:
            x = np.asarray(s['x_scale'], dtype=float)
            y = np.asarray(s['y_scale'], dtype=float)
            if not np.array_equal(x, x_ref):
                # np.interp does not extrapolate — for any x_ref point
                # outside this spectrum's own native range, it silently
                # holds the nearest edge value constant instead. If many
                # spectra share the same narrower range, this creates an
                # artificial flat-then-jump discontinuity at the same
                # x-location across the whole dataset — exactly the kind
                # of consistent feature NMF will "explain" with a
                # dedicated (but spurious) component.
                if x.min() > x_ref_min + _range_tol or x.max() < x_ref_max - _range_tol:
                    mismatched_labels.append(s.get('label', '?'))
                y = np.interp(x_ref, x, y)
            rows.append(y)

        if mismatched_labels:
            self.x_range_mismatch_warning = (
                f"{len(mismatched_labels)} of {len(spectra)} spectra have a "
                f"narrower x-range than the reference spectrum ({spectra[0].get('label', '?')}, "
                f"{x_ref_min:.4g}\u2013{x_ref_max:.4g}). Values outside each spectrum's own "
                "range were held flat (not extrapolated), which can create an artificial "
                "discontinuity that NMF mistakes for a real component. Consider using Data "
                "Range to restrict all spectra to their common overlapping range first."
            )
        else:
            self.x_range_mismatch_warning = None

        X = np.array(rows, dtype=float)
        # NMF requires non-negative input. This shift is necessary for
        # NMF to run at all, but it means W @ H reconstructs X_nn, not the
        # original X — anything comparing a reconstruction back against
        # the original spectrum (e.g. the Reconstruction tab) needs to add
        # this offset back to be a fair comparison.
        # NMF requires non-negative input. Negatives are CLIPPED to zero
        # (this is also exactly what the dialog's negative-values warning
        # tells the user happens).
        #
        # This used to SUBTRACT X.min() instead, shifting the whole dataset
        # up. That looks gentler but is actively harmful: it injects a
        # constant baseline into every spectrum (on the noisy Raman
        # benchmarks, |X.min()| was ~4% of the peak height but the resulting
        # constant had ~24% of the data's total norm), and NMF then has to
        # spend component capacity modelling that flat background, which
        # smears it into the recovered components. Measured against known
        # ground truth, clipping recovers the true components better and fits
        # better: 2-component noisy Raman went from 0.93 to 0.99 similarity
        # (7.8% -> 4.8% lack-of-fit) and 3-component from 0.95 to 0.97
        # (5.7% -> 5.1%). It also makes reference anchoring behave, since a
        # known pure spectrum has no such baseline to match.
        #
        # self.offset is kept (at 0.0) so every offset-aware code path — e.g.
        # the Reconstruction tab adding it back — keeps working unchanged.
        # For genuinely signed data (CD) the clipping is destructive, which is
        # precisely why the dialog warns that NMF is the wrong tool there and
        # points to MCR-ALS with ST non-negativity off.
        self.offset = 0.0
        X_nn = np.clip(X, 0, None)
        # Kept for later reuse by compute_bootstrap_uncertainty() -- the
        # exact aligned, clipped data matrix this fit was run on, needed to
        # build its residuals. Not used anywhere else in compute() itself.
        self.X_nn = X_nn

        if init_H is not None:
            init_H_arr = np.asarray(init_H, dtype=float)
            if init_H_arr.shape != (n_components, X_nn.shape[1]):
                self.last_error = (
                    f"Bootstrap warm-start shape mismatch: expected "
                    f"({n_components}, {X_nn.shape[1]}), got {tuple(init_H_arr.shape)}."
                )
                return False
        else:
            init_H_arr = None

        # --- Reference (known pure-spectrum) anchoring -----------------------
        # references: {component_index: (x_array, y_array)} of KNOWN component
        # spectra. Each is interpolated onto the analysis grid, shifted by the
        # same offset NMF applies to the data (so it lives in the same
        # non-negative space as X_nn), clipped non-negative, and scaled to unit
        # norm (its scale is absorbed into W). Anchoring to what you already
        # know is the most effective way to break NMF's rotational ambiguity.
        ref_rows = {}
        if references:
            for idx, ref in references.items():
                if idx < 0 or idx >= n_components:
                    continue
                rx, ry = ref
                # Same np.interp trap: a reference spectrum can just as easily be
                # stored in descending x order.
                rx, ry = _ascending(rx, ry)
                row = np.interp(x_ref, rx, ry)
                row = np.clip(row, 0, None)
                nrm = np.linalg.norm(row)
                if nrm > 0:
                    row = row / nrm
                ref_rows[idx] = row
        self.reference_components = sorted(ref_rows.keys())
        self.references_fixed = bool(fix_references and ref_rows)

        try:
            if init_H_arr is not None:
                # Bootstrap warm start (see compute()'s init_H docstring) --
                # always routed through the hand-written MU loop, whether or
                # not this fit actually uses reference spectra (ref_rows may
                # be empty here; _fit_with_references handles that fine,
                # since fixed_idx/free_idx are then just [] / all).
                self.W, self.H, self.iterations_used, self.converged = \
                    self._fit_with_references(X_nn, n_components, ref_rows,
                                              bool(fix_references), init,
                                              max_iter, random_state,
                                              init_H=init_H_arr)
                self.reconstruction_error = float(
                    np.linalg.norm(X_nn - self.W @ self.H))
            elif ref_rows:
                # Reference-anchored NMF: plain multiplicative updates (the
                # standard NMF algorithm) with the referenced rows of H held
                # constant when fix_references is on. sklearn's NMF can't hold
                # individual rows fixed, so the loop is written out here; it is
                # the same Lee-&-Seung Frobenius update sklearn itself uses.
                self.W, self.H, self.iterations_used, self.converged = \
                    self._fit_with_references(X_nn, n_components, ref_rows,
                                              bool(fix_references), init,
                                              max_iter, random_state)
                self.reconstruction_error = float(
                    np.linalg.norm(X_nn - self.W @ self.H))
            else:
                model = NMF(n_components=n_components, init=init,
                            max_iter=max_iter, random_state=random_state)
                self.W = model.fit_transform(X_nn)   # (n_spec × n_comp)
                self.H = model.components_           # (n_comp × n_wl)
                self.reconstruction_error = float(model.reconstruction_err_)
                self.iterations_used = int(model.n_iter_)
                # sklearn doesn't expose an explicit converged flag — running
                # the full max_iter budget without sklearn's own internal
                # tolerance being satisfied first is the standard proxy for
                # "may not have converged", same semantics as MCR-ALS's own
                # converged flag.
                self.converged = self.iterations_used < max_iter
            # Percentage-based lack-of-fit, same formula and meaning as
            # MCRALSManager.lof — makes the two methods' status displays
            # directly comparable (reconstruction_error alone is in raw
            # intensity units, which aren't comparable across datasets or
            # against MCR-ALS's percentage scale).
            X_nn_ss = np.sum(X_nn ** 2)
            self.lof = 100.0 * self.reconstruction_error / np.sqrt(X_nn_ss) \
                if X_nn_ss > 0 else 0.0
        except Exception as exc:
            logger.exception("NMFManager: NMF failed")
            # Without this the dialog could only say "NMF failed" with no reason.
            self.last_error = f"NMF failed: {exc}"
            return False

        self.x_axis       = x_ref
        self.labels       = [s['label'] for s in spectra]
        self.n_components = n_components

        # "Percent explained variance" per component: each component's
        # contribution W[:,k] outer H[k], measured by its SQUARED
        # Frobenius norm (variance is a squared quantity), as a share of
        # the SUM of every component's own contribution — not of the
        # actual DATA's own squared norm, which was tried and reverted:
        # NMF fits X_nn = X - offset, not X itself, and when offset is
        # large relative to the real signal, X and X_nn end up on very
        # different absolute scales. Comparing a component (measured in
        # X_nn's scale) against X's own squared norm then produces
        # nonsense in either direction — confirmed directly: one test
        # produced a single component "explaining" 124% of the data on
        # its own, another (with a larger offset) produced ~0.002% for
        # every component despite a good fit. Comparing components only
        # against each other's contributions (all in the same X_nn scale)
        # avoids that mismatch entirely, and has the added benefit of
        # always summing to exactly 100% — no more "why doesn't this add
        # up" confusion, at the cost of these percentages describing each
        # component's SHARE of the modeled signal rather than literally
        # "% of the total data's variance" (a real, if subtle, difference
        # worth being explicit about — see the help doc).
        comp_ss = np.array([
            np.sum((np.outer(self.W[:, k], self.H[k])) ** 2) for k in range(n_components)
        ])
        total_comp_ss = comp_ss.sum()
        self.explained_variance = (100.0 * comp_ss / total_comp_ss) if total_comp_ss > 0 \
                                   else np.zeros(n_components)

        # Components come out of sklearn's NMF in an arbitrary order (not
        # sorted by importance) — reorder everything so "Component 1" is
        # always the most important, "Component 2" the next, etc., matching
        # the usual PCA/factor-analysis convention and making the Elbow
        # plot's meaning (a single aggregate lack-of-fit per component
        # count) independent of this: the elbow was already unaffected by
        # component order, since it never looked at per-component identity
        # in the first place, but the Components/Concentrations tabs
        # weren't consistently ordered before this.
        # EXCEPTION: when the user has anchored specific component slots to
        # known reference spectra, reordering would move their reference out
        # of the slot they assigned it to — keep the fit's slot order so
        # "Component 2 = my known spectrum" stays true.
        if not self.reference_components and init_H_arr is None:
            order = np.argsort(-self.explained_variance)
            self.explained_variance = self.explained_variance[order]
            self.W = self.W[:, order]
            self.H = self.H[order, :]

        # A successful fit means self.W/self.H just changed (new component
        # count, new data, new settings, or a warm-started bootstrap
        # replicate) -- any bootstrap_result computed for the PREVIOUS
        # W/H no longer corresponds to what's loaded now (different
        # shape, or just a different underlying solution) and must not
        # be redrawn against it. Bug found in practice: without this,
        # re-running "Run NMF"/"Run N times, keep best" after a
        # Bootstrap Uncertainty call left the OLD band silently attached
        # to the manager, producing a mismatched/ghosted-looking overlay
        # (or an index error) on the NEXT redraw.
        self.bootstrap_result = None

        logger.info("NMFManager: %d components, reconstruction error=%.4g",
                    n_components, self.reconstruction_error)
        return True

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fit_with_references(X, k, ref_rows, fix, init, max_iter, random_state,
                              init_H=None):
        """Lee & Seung multiplicative-update NMF (Frobenius), with the option
        to hold specific rows of H fixed at known reference spectra.

        Standard NMF updates both factors; here the referenced rows of H are
        simply not updated (or, if fix=False, are used only as the starting
        value and then updated normally like any other row). The free rows of
        H are seeded from the residual left after the references' own best fit,
        so a free component can't start out collinear with a reference and be
        driven to zero. sklearn's NMF cannot hold individual rows fixed, which
        is why the (standard) update loop is written out here.

        init_H : optional (k, n_wl) warm start (see NMFManager.compute()'s
            init_H docstring — this is how NMF bootstrap-uncertainty
            replicates are refit). When given, H starts from it directly
            instead of from the ref_rows/residual-seeding logic below, and
            (if fix) the fixed reference rows are re-imposed on top of it,
            so a warm-started replicate can't drift a "should stay fixed"
            row away from its reference spectrum.
        """
        rng = np.random.RandomState(random_state)
        eps = 1e-10
        m, n = X.shape

        fixed_idx = sorted(ref_rows.keys())
        free_idx = [j for j in range(k) if j not in ref_rows]

        if init_H is not None:
            H = np.asarray(init_H, dtype=float).copy()
            if fix:
                for j, row in ref_rows.items():
                    H[j] = row
        else:
            H = np.zeros((k, n))
            for j, row in ref_rows.items():
                H[j] = row
            if free_idx:
                # Residual after the references explain what they can — seed
                # the free rows from the structure they DON'T explain.
                Hf = np.array([ref_rows[j] for j in fixed_idx])
                Wf = np.clip(X @ np.linalg.pinv(Hf), 0, None)
                R = np.clip(X - Wf @ Hf, 0, None)
                for j in free_idx:
                    seed = R.mean(axis=0) if R.any() else X.mean(axis=0)
                    seed = seed * (1.0 + 0.1 * rng.rand(n))
                    nrm = np.linalg.norm(seed)
                    H[j] = seed / nrm if nrm > 0 else rng.rand(n)
        H = np.clip(H, eps, None)
        W = np.clip(X @ np.linalg.pinv(H), eps, None)

        prev_err = None
        iters = max_iter
        converged = False
        for it in range(max_iter):
            # W update (W is always free)
            W = W * ((X @ H.T) / ((W @ H) @ H.T + eps))
            W = np.clip(W, eps, None)

            # H update — the fixed rows are simply not updated
            H_new = H * ((W.T @ X) / ((W.T @ W) @ H + eps))
            if fix:
                for j in fixed_idx:
                    H_new[j] = H[j]
            H = np.clip(H_new, eps, None)

            err = float(np.linalg.norm(X - W @ H))
            if prev_err is not None and prev_err > 0 \
                    and abs(prev_err - err) / prev_err < 1e-6:
                iters = it + 1
                converged = True
                break
            prev_err = err
        return W, H, iters, converged

    def _autofit_excel_columns(self, writer, sheet_name, df):
        """Widen each column enough to show its full header on first open
        — same fix applied to PCA/SVD's Excel export."""
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns):
            width = max(len(str(col)) + 2, 10)
            worksheet.column_dimensions[get_column_letter(i + 1)].width = width

    def _build_export_frames(self, include_components, include_scores, include_info):
        """Shared DataFrame construction for both Excel and text export."""
        import pandas as pd
        n = self.n_components

        components_df = None
        if include_components:
            comp_dict = {'x': self.x_axis}
            for k in range(n):
                comp_dict[f'NMF {k+1}'] = self.H[k]
            components_df = pd.DataFrame(comp_dict)

        scores_df = None
        if include_scores:
            scores_dict = {'Spectrum': self.labels}
            for k in range(n):
                scores_dict[f'NMF {k+1}'] = self.W[:, k]
            scores_df = pd.DataFrame(scores_dict)

        info_df = None
        if include_info:
            info_df = pd.DataFrame({
                'Component': [f'NMF {k+1}' for k in range(n)],
                'Explained_variance_pct': self.explained_variance,
            })

        return components_df, scores_df, info_df

    def save_results_excel(self, filepath, include_components=True,
                            include_scores=True, include_info=True):
        """Save Components/Scores/Info to one Excel workbook with separate
        worksheets. Raises on failure so the controller can surface a
        message — same contract as PcaScoresManager/SVDAnalysisManager's
        save_results_excel."""
        import pandas as pd
        if self.H is None:
            raise ValueError("No NMF data available to save")

        components_df, scores_df, info_df = self._build_export_frames(
            include_components, include_scores, include_info)

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            if components_df is not None:
                components_df.to_excel(writer, sheet_name='Components', index=False)
                self._autofit_excel_columns(writer, 'Components', components_df)
            if scores_df is not None:
                scores_df.to_excel(writer, sheet_name='Scores', index=False)
                self._autofit_excel_columns(writer, 'Scores', scores_df)
            if info_df is not None:
                # Reconstruction error doesn't fit the per-component table
                # shape, so it's appended as an extra row pair rather than
                # a separate sheet, for a one-glance summary.
                info_df.to_excel(writer, sheet_name='Info', index=False)
                ws = writer.sheets['Info']
                ws.append([])
                ws.append(['Reconstruction error', float(self.reconstruction_error)])
                self._autofit_excel_columns(writer, 'Info', info_df)
        return True

    def save_results_text(self, save_config):
        """Save Components/Scores/Info to text/CSV file(s) based on
        save_config (file_path, delimiter, precision, save_separate,
        include_components, include_scores, include_info)."""
        if self.H is None:
            raise ValueError("No NMF data available to save")

        file_path = save_config['file_path']
        delimiter = save_config.get('delimiter', '\t')
        precision = save_config.get('precision', 6)
        float_format = f'%.{precision}f'
        include_components = save_config.get('include_components', True)
        include_scores = save_config.get('include_scores', True)
        include_info = save_config.get('include_info', True)

        components_df, scores_df, info_df = self._build_export_frames(
            include_components, include_scores, include_info)

        if save_config.get('save_separate'):
            base = os.path.splitext(file_path)[0]
            if components_df is not None:
                components_df.to_csv(f'{base}_components.txt', sep=delimiter, index=False, float_format=float_format)
            if scores_df is not None:
                scores_df.to_csv(f'{base}_scores.txt', sep=delimiter, index=False, float_format=float_format)
            if info_df is not None:
                with open(f'{base}_info.txt', 'w', newline='') as f:
                    info_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write(f'\nReconstruction error{delimiter}{self.reconstruction_error:.6g}\n')
        else:
            with open(file_path, 'w', newline='') as f:
                if components_df is not None:
                    f.write('# Components\n')
                    components_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write('\n')
                if scores_df is not None:
                    f.write('# Scores\n')
                    scores_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write('\n')
                if info_df is not None:
                    f.write('# Info\n')
                    info_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write(f'\nReconstruction error{delimiter}{self.reconstruction_error:.6g}\n')
        return True
