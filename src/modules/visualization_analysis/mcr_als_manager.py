# src/modules/visualization_analysis/mcr_als_manager.py
"""
Multivariate Curve Resolution - Alternating Least Squares (MCR-ALS) manager.

Decomposes a spectral matrix D (n_spectra x n_wavelengths) into:
    C  : (n_spectra x n_components)   — concentration/abundance profiles
    ST : (n_components x n_wavelengths) — pure component spectra

D ~= C @ ST, found by alternating constrained least-squares fits: given ST,
solve for C; given the new C, solve for ST; repeat until the fit stops
improving. Unlike NMF (which enforces non-negativity via a specific
multiplicative-update algorithm baked into the fit itself), MCR-ALS applies
non-negativity as an explicit constraint at each step via NNLS, which is
more flexible — e.g. it's straightforward to turn either constraint off
independently, unlike NMF where non-negativity of both factors is
structural.
"""

import os
import numpy as np
from scipy.optimize import nnls
from src.modules.utils.app_logger import get_logger
from src.modules.utils.spectra_validation import axes_match

logger = get_logger(__name__)


class MCRALSManager:

    def __init__(self):
        self.C            = None   # (n_spectra x n_comp) — concentration profiles
        self.ST           = None   # (n_comp x n_wl) — pure component spectra
        self.x_axis       = None
        self.labels       = []
        self.n_components = None
        self.lof          = None   # lack-of-fit, % — sqrt(sum((D-Chat)^2)/sum(D^2))*100
        self.explained_variance = None   # % of the DATA's own squared norm
        self.reference_components = []    # component slots anchored to known spectra
        self.references_fixed = False     # whether those slots were held constant
                                          # explained by each component's
                                          # contribution (C[:,k] outer ST[k]),
                                          # PCA-style — NOT ST's own norm
                                          # (uninformative once
                                          # normalize_spectra forces every row
                                          # to unit norm) and NOT normalized
                                          # against the components' own sum
                                          # (a different, less standard
                                          # convention this used briefly).
                                          # Doesn't necessarily sum to 100%,
                                          # since components aren't
                                          # constrained to be orthogonal.
        self.iterations_used    = None
        self.converged          = False
        self.x_range_mismatch_warning = None
        self.last_error = None

    def reset(self):
        """Clear all previous results — same purpose as reset() on every
        other visualization-analysis manager."""
        self.__init__()

    def compute(self, spectra: list, n_components: int,
                init: str = 'svd', max_iterations: int = 100, tol: float = 0.01,
                c_nonneg: bool = True, st_nonneg: bool = True,
                normalize_spectra: bool = True, closure: bool = False,
                random_state: int = 42,
                references: dict = None, fix_references: bool = False) -> bool:
        """
        Run MCR-ALS on the selected spectra.

        Parameters
        ----------
        spectra : list of spectrum dicts
        n_components : number of components to resolve
        init : 'svd' (deterministic, from the absolute value of the leading
            right-singular vectors of D) or 'random'
        max_iterations : maximum ALS iterations
        tol : stop early once the lack-of-fit changes by less than this
            (percentage points) between consecutive iterations
        c_nonneg, st_nonneg : apply non-negativity (via NNLS) to C and/or
            ST independently at each iteration
        normalize_spectra : rescale each component's ST row to unit norm
            every iteration, pushing the compensating scale factor into C.
            C @ ST is unaffected by C *= k, ST /= k for any k, so without
            this the two factors can drift to arbitrarily large/small
            scales over iterations; this keeps that ambiguity pinned down.
            Ignored when closure=True (see below — closure already pins
            down the same ambiguity by construction).
        closure : apply a genuine closure constraint DURING the fit —
            every spectrum's concentration row is projected onto "sums to
            1" immediately after each C-update, and the spectra update
            that follows adapts to that constrained C through the
            iterations. This is different from (and more rigorous than)
            just dividing an already-computed C by its own row sums after
            the fact: that post-hoc version has no single compensating
            rescale of ST that keeps C @ ST unchanged, since ST is shared
            across every spectrum while the needed correction differs per
            spectrum. Applying it during the fit instead means C
            genuinely sums to 1 per row AND the reported lack-of-fit
            reflects the real, self-consistent, constrained fit — at the
            cost of some fit quality, since closure is a real constraint
            that reduces the model's flexibility (worth it only if you
            have genuine reason to believe closure holds physically, e.g.
            real mass balance across your components).
        random_state : seed, used only for init='random'

        Returns True on success.
        """
        if not spectra:
            return False

        self.last_error = None

        # Build data matrix, aligning onto a common x-grid the same way
        # NMFManager does, with the same non-overlap hard-block and
        # narrower-range soft-warning.
        x_ref_check = np.asarray(spectra[0]['x_scale'], dtype=float)
        ref_min, ref_max = x_ref_check.min(), x_ref_check.max()
        for s in spectra[1:]:
            x_check = np.asarray(s['x_scale'], dtype=float)
            s_min, s_max = x_check.min(), x_check.max()
            if s_max < ref_min or s_min > ref_max:
                self.last_error = (
                    f"Spectra have non-overlapping x-axis ranges \u2014 cannot run "
                    f"MCR-ALS.\n\nReference spectrum ('{spectra[0].get('label', '?')}'): "
                    f"{ref_min:.4g} to {ref_max:.4g}\n"
                    f"Spectrum '{s.get('label', '?')}': {s_min:.4g} to {s_max:.4g}\n\n"
                    "These do not overlap at all, so there's no shared x-range for "
                    "MCR-ALS to decompose. Please select only spectra that cover the "
                    "same spectral region."
                )
                return False

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
        # have a meaningfully different range at all.
        if x_ref.size > 1:
            _step = float(np.median(np.abs(np.diff(x_ref))))
            _range_tol = _step * 1e-6 if np.isfinite(_step) and _step > 0 else 1e-9
        else:
            _range_tol = 1e-9
        rows = []
        mismatched_labels = []
        for s in spectra:
            x = np.asarray(s['x_scale'], dtype=float)
            y = np.asarray(s['y_scale'], dtype=float)
            if not np.array_equal(x, x_ref):
                if x.min() > x_ref_min + _range_tol or x.max() < x_ref_max - _range_tol:
                    mismatched_labels.append(s.get('label', '?'))
                y = np.interp(x_ref, x, y)
            rows.append(y)

        if mismatched_labels:
            self.x_range_mismatch_warning = (
                f"{len(mismatched_labels)} of {len(spectra)} spectra have a narrower "
                f"x-range than the reference spectrum ({spectra[0].get('label', '?')}, "
                f"{x_ref_min:.4g}\u2013{x_ref_max:.4g}). Values outside each spectrum's own "
                "range were held flat (not extrapolated), which can create an artificial "
                "discontinuity that MCR-ALS mistakes for a real component. Consider using "
                "Data Range to restrict all spectra to their common overlapping range first."
            )
        else:
            self.x_range_mismatch_warning = None

        D = np.array(rows, dtype=float)   # (m, n)
        m, n = D.shape

        max_possible = min(m, n)
        if n_components < 1 or n_components > max_possible:
            self.last_error = (
                f"Components must be between 1 and {max_possible} "
                f"(limited by min(number of spectra, number of wavelength points))."
            )
            return False

        try:
            rng = np.random.RandomState(random_state)

            # --- Reference (known pure-spectrum) anchoring -------------------
            # references: {component_index: (x_array, y_array)} of KNOWN pure
            # spectra. Each is interpolated onto the analysis x-grid and, in
            # the NON-closure case, scaled to unit norm to match this
            # manager's unit-norm convention for ST rows there (see
            # normalize_spectra below) — so its scale lives in C rather than
            # in the fixed shape. Used to (a) seed those ST rows and, if
            # fix_references, (b) hold them constant at every iteration so
            # the resolved decomposition is anchored to what you already
            # know — the single most effective way to break MCR's
            # rotational ambiguity.
            #
            # BUG FIX: that unit-norm rescale used to happen unconditionally,
            # including when closure=True. Under closure, C's rows are
            # constrained to sum to exactly 1 — a genuine absolute-scale
            # constraint, not a free ambiguity for the fit to resolve however
            # it likes (that's why normalize_spectra is itself skipped below
            # when closure is on: "closure already pins down the same
            # ambiguity by construction"). Forcibly rescaling ONLY the fixed
            # reference row to an arbitrary unit norm, while the free rows
            # were left to find whatever their natural closure-constrained
            # scale is (which is NOT unit norm — it tracks the data's own
            # magnitude), created a scale mismatch between the fixed and free
            # components that closure's sum-to-1 constraint cannot correct
            # (concentrations can't exceed 1 to compensate for an
            # undersized fixed spectrum). Measured effect on a real
            # benchmark: lack-of-fit went from 0.11% (no reference) to
            # 59.8% (reference fixed, closure on, before this fix), with the
            # referenced component's concentration pinned near its ceiling
            # everywhere instead of tracking its true profile. Skipping the
            # rescale under closure — using the reference at whatever
            # absolute scale it was measured at, which is the same scale as
            # every other selected spectrum — resolves this (0.18% lack of
            # fit on the same case, matching the un-referenced run).
            ref_rows = {}
            if references:
                for idx, ref in references.items():
                    if idx < 0 or idx >= n_components:
                        continue
                    rx, ry = ref
                    # Same np.interp trap: a reference spectrum can just as easily
                    # be stored in descending x order.
                    rx, ry = _ascending(rx, ry)
                    ry_on_grid = np.interp(x_ref, rx, ry)
                    if not closure:
                        nrm = np.linalg.norm(ry_on_grid)
                        if nrm > 0:
                            ry_on_grid = ry_on_grid / nrm
                    ref_rows[idx] = ry_on_grid
            self.reference_components = sorted(ref_rows.keys())
            self.references_fixed = bool(fix_references and ref_rows)

            def _impose_refs(ST_mat):
                for idx, row in ref_rows.items():
                    ST_mat[idx, :] = row
                return ST_mat

            if init == 'random':
                # For non-negative spectra a positive random start is right.
                # For SIGNED spectra (CD, ROA, VCD) it is not: an all-positive
                # basis cannot represent negative bands, and the non-negative
                # C-solve then drives the concentrations to zero (see below).
                ST = rng.rand(n_components, n) if st_nonneg \
                    else rng.randn(n_components, n)
            else:
                # SVD-based initial guess: the leading right-singular vectors
                # capture the dominant spectral shapes.
                _, _, Vt = np.linalg.svd(D, full_matrices=False)
                ST = Vt[:n_components, :]
                if st_nonneg:
                    # Only legitimate when the pure spectra really are
                    # non-negative: abs() gives a usable non-negative start.
                    ST = np.abs(ST)

            if not st_nonneg:
                # BUG FIX (signed data). The initial guess used to be abs()'d
                # unconditionally, which throws away the sign structure and
                # leaves an all-positive basis. For genuinely signed spectra
                # (CD, ROA, VCD) that is fatal: a signed spectrum cannot be
                # built from positive-only shapes with NON-NEGATIVE
                # concentrations, so the very first NNLS C-solve returned all
                # zeros, every component died, and the fit collapsed to
                # lack-of-fit = 100%. Keeping the signed singular vectors fixes
                # that.
                #
                # A singular vector's sign is arbitrary, though, while C is
                # constrained >= 0 — so a row pointing "the wrong way" would
                # still be zeroed out by NNLS. Orient each row so its projection
                # onto the data is predominantly positive, giving the
                # non-negative C-solve something it can actually use.
                for k_ in range(n_components):
                    if np.sum(D @ ST[k_]) < 0:
                        ST[k_] = -ST[k_]

            # Seed the referenced rows with the known spectra (whether or
            # not they'll be held fixed — a good starting point either way).
            if ref_rows:
                ST = _impose_refs(ST)
                # When the references are HELD FIXED, initialise the free
                # rows from the residual left after subtracting the best fit
                # of the fixed references, rather than from raw SVD/random.
                # Otherwise a poor free-row guess can be so collinear with a
                # fixed reference that the very first non-negative C-solve
                # assigns the free component ZERO concentration, killing it
                # permanently and leaving only the references to fit (which
                # was producing a spuriously huge lack-of-fit). Seeding from
                # the residual guarantees the free rows start on the part of
                # the data the references don't already explain.
                if fix_references:
                    _fixed = sorted(ref_rows.keys())
                    _free = [j for j in range(n_components) if j not in ref_rows]
                    if _free:
                        ST_fx = np.array([ref_rows[i] for i in _fixed])
                        C_fx = D @ np.linalg.pinv(ST_fx)
                        R = D - C_fx @ ST_fx
                        _, _, VtR = np.linalg.svd(R, full_matrices=False)
                        for pos, idx in enumerate(_free):
                            base = VtR[pos] if pos < VtR.shape[0] else rng.rand(n)
                            if st_nonneg:
                                ST[idx, :] = np.abs(base)
                            else:
                                # Signed data: the residual singular vector's
                                # sign is arbitrary, but the C-solve forces
                                # concentrations >= 0. Orient the row so its
                                # own projection onto the residual is mostly
                                # positive, so the first non-negative C-solve
                                # doesn't immediately zero the component out.
                                proj = R @ base
                                if np.sum(proj) < 0:
                                    base = -base
                                if init == 'random':
                                    base = base + 0.05 * rng.rand(n)
                                ST[idx, :] = base

            C = np.zeros((m, n_components))
            prev_lof = None
            converged = False
            iterations_used = 0

            for it in range(max_iterations):
                # Solve for C given ST.
                if c_nonneg:
                    C = np.zeros((m, n_components))
                    for i in range(m):
                        c_i, _ = nnls(ST.T, D[i, :])
                        C[i, :] = c_i
                else:
                    C = D @ np.linalg.pinv(ST)

                if closure:
                    # True closure constraint: project each spectrum's
                    # concentration row onto "sums to 1" BEFORE the ST
                    # update below, so ST adapts to the constrained C
                    # through the iterations — this is what makes it a
                    # real constraint on the fit itself, not a display
                    # trick applied after the fact. A row summing to
                    # (numerically) zero is left alone rather than
                    # divided by zero — vanishingly rare for real data
                    # with c_nonneg on, but guarded defensively.
                    row_sums = C.sum(axis=1, keepdims=True)
                    safe = row_sums.flatten() > 1e-12
                    C[safe] = C[safe] / row_sums[safe]

                # Solve for ST given the new C.
                if self.references_fixed:
                    # Hold the referenced rows constant and solve ONLY the
                    # free rows against the residual left after removing the
                    # fixed rows' contribution — otherwise the free rows get
                    # fit against a wrong (free) version of the anchored rows
                    # and the anchored fit falls apart.
                    fixed_idx = sorted(ref_rows.keys())
                    free_idx = [j for j in range(n_components) if j not in ref_rows]
                    ST = _impose_refs(ST)
                    ST_fixed = np.array([ref_rows[i] for i in fixed_idx])
                    D_resid = D - C[:, fixed_idx] @ ST_fixed
                    if free_idx:
                        C_free = C[:, free_idx]
                        if st_nonneg:
                            for jj in range(n):
                                st_j, _ = nnls(C_free, D_resid[:, jj])
                                for pos, idx in enumerate(free_idx):
                                    ST[idx, jj] = st_j[pos]
                        else:
                            ST_free = np.linalg.pinv(C_free) @ D_resid
                            for pos, idx in enumerate(free_idx):
                                ST[idx, :] = ST_free[pos, :]
                elif st_nonneg:
                    ST = np.zeros((n_components, n))
                    for j in range(n):
                        st_j, _ = nnls(C, D[:, j])
                        ST[:, j] = st_j
                else:
                    ST = np.linalg.pinv(C) @ D

                if normalize_spectra and not closure:
                    # Mutually exclusive with closure: normalize_spectra
                    # rescales ST row norms and pushes the compensating
                    # factor into C, which would immediately undo the
                    # closure projection above. Closure already pins down
                    # the C/ST scale ambiguity by itself (each row of C
                    # sums to exactly 1), so there's nothing left for this
                    # step to usefully do when closure is on.
                    norms = np.linalg.norm(ST, axis=1)
                    norms[norms == 0] = 1.0
                    ST = ST / norms[:, None]
                    C = C * norms[None, :]

                # Hold the referenced rows constant (after normalisation, so
                # they stay at their fixed unit-norm shape); C above has
                # already adapted to them via the least-squares/NNLS solve.
                if self.references_fixed:
                    ST = _impose_refs(ST)

                D_hat = C @ ST
                denom = np.sum(D ** 2)
                lof = 100.0 * np.sqrt(np.sum((D - D_hat) ** 2) / denom) if denom > 0 else 0.0
                iterations_used = it + 1

                if prev_lof is not None and abs(prev_lof - lof) < tol:
                    prev_lof = lof
                    converged = True
                    break
                prev_lof = lof

        except Exception as exc:
            logger.error("MCRALSManager: MCR-ALS failed: %s", exc)
            self.last_error = str(exc)
            return False

        self.C            = C
        self.ST           = ST
        self.x_axis       = x_ref
        self.labels       = [s.get('label', f'Spectrum {i+1}') for i, s in enumerate(spectra)]
        self.n_components = n_components
        self.lof          = prev_lof
        self.iterations_used = iterations_used
        self.converged    = converged

        # "Percent explained variance" per component: each component's
        # contribution D_k = C[:,k] outer ST[k], measured by its SQUARED
        # Frobenius norm (variance is a squared quantity), as a share of
        # the SUM of every component's own contribution — not of the
        # actual DATA's own squared norm, which this used to do and was
        # reverted (same fix, same reasoning, as NMFManager — see there
        # for the concrete case that broke it: NMF's offset shift made
        # that comparison scale-inconsistent; MCR-ALS has no such offset,
        # but for consistency between the two methods, and because
        # "these numbers don't add up to 100%" reads as a bug even when
        # it technically isn't, both now use the same convention). This
        # is definitionally guaranteed to sum to exactly 100% — no more
        # "why doesn't this add up" confusion — at the cost of these
        # percentages describing each component's SHARE of the modeled
        # signal rather than literally "% of the total data's variance."
        comp_ss = np.array([
            np.sum((np.outer(C[:, k], ST[k])) ** 2) for k in range(n_components)
        ])
        total_comp_ss = comp_ss.sum()
        self.explained_variance = (100.0 * comp_ss / total_comp_ss) if total_comp_ss > 0 \
                                   else np.zeros(n_components)

        # The ALS/NNLS fit doesn't come out ordered by importance either —
        # reorder everything so "Component 1" is always the most
        # important, matching NMFManager's identical fix and the usual
        # PCA/factor-analysis convention. EXCEPTION: when the user has
        # anchored specific component slots to known reference spectra,
        # reordering would move their reference out of the slot they
        # assigned it to — so we keep the fit's slot order intact in that
        # case, so "Component 2 = my known spectrum" stays true.
        if self.reference_components:
            self.explained_variance = self.explained_variance
        else:
            order = np.argsort(-self.explained_variance)
            self.explained_variance = self.explained_variance[order]
            self.C = self.C[:, order]
            self.ST = self.ST[order, :]

        logger.info("MCRALSManager: %d components, LOF=%.4g%%, %d iterations, converged=%s",
                    n_components, self.lof, iterations_used, converged)
        return True

    # ------------------------------------------------------------------ #
    # Export                                                               #
    # ------------------------------------------------------------------ #

    def _autofit_excel_columns(self, writer, sheet_name, df):
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df.columns):
            width = max(len(str(col)) + 2, 10)
            worksheet.column_dimensions[get_column_letter(i + 1)].width = width

    def _build_export_frames(self, include_spectra, include_concentrations, include_info):
        import pandas as pd
        n = self.n_components

        spectra_df = None
        if include_spectra:
            comp_dict = {'x': self.x_axis}
            for k in range(n):
                comp_dict[f'MCR {k+1}'] = self.ST[k]
            spectra_df = pd.DataFrame(comp_dict)

        conc_df = None
        if include_concentrations:
            conc_dict = {'Spectrum': self.labels}
            for k in range(n):
                conc_dict[f'MCR {k+1}'] = self.C[:, k]
            conc_df = pd.DataFrame(conc_dict)

        info_df = None
        if include_info:
            info_df = pd.DataFrame({
                'Component': [f'MCR {k+1}' for k in range(n)],
                'Explained_variance_pct': self.explained_variance,
            })

        return spectra_df, conc_df, info_df

    def save_results_excel(self, filepath, include_spectra=True,
                            include_concentrations=True, include_info=True):
        import pandas as pd
        if self.ST is None:
            raise ValueError("No MCR-ALS data available to save")

        spectra_df, conc_df, info_df = self._build_export_frames(
            include_spectra, include_concentrations, include_info)

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            if spectra_df is not None:
                spectra_df.to_excel(writer, sheet_name='Pure_Spectra', index=False)
                self._autofit_excel_columns(writer, 'Pure_Spectra', spectra_df)
            if conc_df is not None:
                conc_df.to_excel(writer, sheet_name='Concentrations', index=False)
                self._autofit_excel_columns(writer, 'Concentrations', conc_df)
            if info_df is not None:
                info_df.to_excel(writer, sheet_name='Info', index=False)
                ws = writer.sheets['Info']
                ws.append([])
                ws.append(['Lack of fit (%)', float(self.lof)])
                ws.append(['Iterations', int(self.iterations_used)])
                ws.append(['Converged', bool(self.converged)])
                self._autofit_excel_columns(writer, 'Info', info_df)
        return True

    def save_results_text(self, save_config):
        if self.ST is None:
            raise ValueError("No MCR-ALS data available to save")

        file_path = save_config['file_path']
        delimiter = save_config.get('delimiter', '\t')
        precision = save_config.get('precision', 6)
        float_format = f'%.{precision}f'
        include_spectra = save_config.get('include_spectra', True)
        include_concentrations = save_config.get('include_concentrations', True)
        include_info = save_config.get('include_info', True)

        spectra_df, conc_df, info_df = self._build_export_frames(
            include_spectra, include_concentrations, include_info)

        if save_config.get('save_separate'):
            base = os.path.splitext(file_path)[0]
            if spectra_df is not None:
                spectra_df.to_csv(f'{base}_pure_spectra.txt', sep=delimiter, index=False, float_format=float_format)
            if conc_df is not None:
                conc_df.to_csv(f'{base}_concentrations.txt', sep=delimiter, index=False, float_format=float_format)
            if info_df is not None:
                with open(f'{base}_info.txt', 'w', newline='') as f:
                    info_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write(f'\nLack of fit (%){delimiter}{self.lof:.6g}\n')
                    f.write(f'Iterations{delimiter}{self.iterations_used}\n')
                    f.write(f'Converged{delimiter}{self.converged}\n')
        else:
            with open(file_path, 'w', newline='') as f:
                if spectra_df is not None:
                    f.write('# Pure_Spectra\n')
                    spectra_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write('\n')
                if conc_df is not None:
                    f.write('# Concentrations\n')
                    conc_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write('\n')
                if info_df is not None:
                    f.write('# Info\n')
                    info_df.to_csv(f, sep=delimiter, index=False, float_format=float_format)
                    f.write(f'\nLack of fit (%){delimiter}{self.lof:.6g}\n')
                    f.write(f'Iterations{delimiter}{self.iterations_used}\n')
                    f.write(f'Converged{delimiter}{self.converged}\n')
        return True
