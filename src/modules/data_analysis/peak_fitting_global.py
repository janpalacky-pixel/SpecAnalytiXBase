# src/modules/data_analysis/peak_fitting_global.py
"""Peak Fitting: a global fit of a series (Qt-free). All selected spectra
are fitted together with ONE set of peaks: the positions and widths (and
Voigt / Pseudo-Voigt's extra value) are the same for all spectra - or, with
share='widths', only the widths, each spectrum with its own positions -
while every spectrum has its own heights and its own background. For a noisy
series (a temperature scan, a titration) this is far more stable than
fitting each spectrum alone: the positions and widths are determined by all
spectra together, each spectrum only has to give its heights.

How: variable projection. The heights and the background enter the model
linearly; for given positions and widths they are found exactly by linear
least squares, spectrum by spectrum (with bounds for Positive / Negative
Peaks Only). Only the positions and widths are fitted non-linearly
(scipy.optimize.least_squares, its Jacobian estimated with a sparsity
pattern: a spectrum's own positions only change that spectrum). Fixed and
linked values of the starting peaks (peak['constraints'], see
peak_fitting_manager.PARAM_NAMES) apply to every spectrum. The
uncertainties come from the covariance of all values (non-linear and
linear) of the whole fit.

The results have the form of peak_fitting_series (one dict per spectrum:
label, ok, peaks, r2, background) plus 'global': the kind of sharing, so the
Series results, the plot views and the outputs of the window work as for a
series fitted spectrum by spectrum. The window is
src/views/dialogs/data_analysis/peak_fitting_dialog.py (Several spectra:
Together ...)."""

import numpy as np

from src.modules.data_analysis.peak_fitting_manager import (
    PeakFittingManager, PARAM_NAMES, _constraint_plan, _expand, resolve_background)
from src.modules.utils.app_logger import get_logger

logger = get_logger(__name__)

SHARES = (('each', "Each on its own"),
          ('positions', "Together: the same positions and widths"),
          ('widths', "Together: the same widths"))
SHARE_TEXT = {'positions': "the same positions and widths", 'widths': "the same widths"}


def _xy(spectrum):
    x = np.asarray(spectrum.get('x_scale', []), dtype=float)
    y = np.asarray(spectrum.get('y_scale', []), dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    return x[good], y[good]


class _Problem:
    """The global fit of `spectra` from the starting peaks `template`."""

    def __init__(self, spectra, template, share, constraints, background, manager):
        self.m = manager
        self.share = share
        self.data = [_xy(s) for s in spectra]
        self.labels = [str(s.get('label', '')) for s in spectra]
        self.template = [dict(p) for p in template]
        self.defs = [(p['model'], len(manager.peak_models[p['model']][1]))
                     for p in self.template]
        self.n_full = sum(n for _, n in self.defs)
        self.offset = np.cumsum([0] + [n for _, n in self.defs])[:-1]
        self.plan = _constraint_plan(self.template, self.defs)
        self.constraints = list(constraints)
        # start values of all parameters (template layout: height, center, width, extra)
        start = []
        for p, (model, n) in zip(self.template, self.defs):
            w = abs(float(p['width']))
            vals = [float(p['amplitude']), float(p['center']), w]
            if n > 3:
                vals += [v for v, _, _ in manager.get_extra_param_defaults(model, w, p)]
            start += vals
        self.start = np.array(start, dtype=float)
        # the backgrounds, chosen for each spectrum (Automatic: from its data)
        self.bg_kind = [resolve_background(x, y, background) for x, y in self.data]
        self.bg_range = [(float(x.min()), float(x.max())) if x.size else (0.0, 1.0)
                         for x, _ in self.data]
        # which parameter is what
        self.kind_of = []            # per full index: 'height' / 'center' / 'width' / 'extra'
        for model, n in self.defs:
            self.kind_of += list(PARAM_NAMES[:n])
        self.free_nl = [i for i, p in enumerate(self.plan)
                        if p is None and self.kind_of[i] != 'height']
        self.per_spectrum = [i for i in self.free_nl
                             if share == 'widths' and self.kind_of[i] == 'center']
        self.shared = [i for i in self.free_nl if i not in self.per_spectrum]
        # heights: free ones are the linear unknowns; linked ones follow
        # their root (a free or fixed height) times a factor
        self.height_root = {}
        for k in range(len(self.template)):
            i = self.offset[k]
            root, factor, seen = i, 1.0, set()
            while self.plan[root] is not None and self.plan[root][0] == 'link' \
                    and root not in seen:
                seen.add(root)
                factor *= self.plan[root][3]
                root = self.plan[root][1]
            self.height_root[i] = (root, factor)
        self.free_heights = [i for i in (self.offset[k] for k in range(len(self.template)))
                             if self.plan[i] is None]
        self._bounds()

    # -- the non-linear parameters theta = shared + per spectrum (spectrum by spectrum)
    def n_theta(self):
        return len(self.shared) + len(self.per_spectrum) * len(self.data)

    def _theta_index(self, s, i):
        if i in self.shared:
            return self.shared.index(i)
        return len(self.shared) + s * len(self.per_spectrum) + self.per_spectrum.index(i)

    def _bounds(self):
        xs = np.concatenate([x for x, _ in self.data]) if self.data else np.zeros(1)
        x_lo, x_hi = float(xs.min()), float(xs.max())
        width_cap = (x_hi - x_lo) / 2.0 if x_hi > x_lo else np.inf
        lo, hi, t0 = [], [], []
        order = [(None, i) for i in self.shared] + [(s, i) for s in range(len(self.data))
                                                     for i in self.per_spectrum]
        for _, i in order:
            k = int(np.searchsorted(self.offset, i, side='right') - 1)
            model = self.defs[k][0]
            w = abs(float(self.start[self.offset[k] + 2])) or 1.0
            v = float(self.start[i])
            name = self.kind_of[i]
            if name == 'center':
                a, b = max(v - 2 * w, x_lo), min(v + 2 * w, x_hi)
                if a >= b:
                    a, b = v - 2 * w, v + 2 * w
            elif name == 'width':
                a, b = 1e-6, min(w * 10, width_cap)
                v = min(v, b * 0.999)
            elif model == 'Pseudo-Voigt':
                a, b = 0.0, 1.0
            else:
                a, b = 1e-6, w * 10
            lo.append(a)
            hi.append(b)
            t0.append(float(np.clip(v, a, b)))
        self.lo, self.hi, self.theta0 = np.array(lo), np.array(hi), np.array(t0)

    def full_nonlinear(self, s, theta):
        """All parameters of spectrum s from theta (heights: their start, to
        be replaced by the linear solution)."""
        q = np.array([theta[self._theta_index(s, i)] for i in self.free_nl], dtype=float)
        plan = [('fixed',) if self.kind_of[i] == 'height' else p for i, p in enumerate(self.plan)]
        return _expand(plan, self.start, np.array(self.free_nl, dtype=int), q)

    def design(self, s, theta):
        """(A, constant, columns, full): the model of spectrum s is A @ c +
        constant; columns says what each c is ('h', i) or ('bg', j)."""
        x, _ = self.data[s]
        full = self.full_nonlinear(s, theta)
        shapes = {}
        for k, (model, n) in enumerate(self.defs):
            i = self.offset[k]
            params = full[i:i + n].copy()
            params[0] = 1.0
            shapes[i] = self.m.peak_models[model][0](x, *params)
        cols, names = [], []
        constant = np.zeros_like(x)
        for i in self.free_heights:
            col = np.zeros_like(x)
            for j, (root, factor) in self.height_root.items():
                if root == i:
                    col = col + factor * shapes[j]
            cols.append(col)
            names.append(('h', i))
        for j, (root, factor) in self.height_root.items():
            if root not in self.free_heights:              # fixed (or a broken link)
                constant = constant + factor * float(self.start[root]) * shapes[j]
        kind = self.bg_kind[s]
        if kind in ('constant', 'linear'):
            x0, x1 = self.bg_range[s]
            t = (x - x0) / (x1 - x0) if x1 > x0 else np.zeros_like(x)
            if kind == 'constant':
                cols.append(np.ones_like(x))
                names.append(('bg', 0))
            else:
                cols += [1.0 - t, t]
                names += [('bg', 0), ('bg', 1)]
        A = np.column_stack(cols) if cols else np.zeros((x.size, 0))
        return A, constant, names, full

    def solve_linear(self, s, A, rhs):
        from scipy.optimize import lsq_linear
        if A.shape[1] == 0:
            return np.zeros(0)
        constraint = self.constraints[s] if s < len(self.constraints) else 'unrestricted'
        if constraint in ('positive', 'negative'):
            lo = np.full(A.shape[1], -np.inf)
            hi = np.full(A.shape[1], np.inf)
            for c, i in enumerate(self.free_heights):
                if constraint == 'positive':
                    lo[c] = 0.0
                else:
                    hi[c] = 0.0
            return lsq_linear(A, rhs, bounds=(lo, hi), method='bvls').x
        return np.linalg.lstsq(A, rhs, rcond=None)[0]

    def residuals(self, theta):
        out = []
        for s, (x, y) in enumerate(self.data):
            A, const, _, _ = self.design(s, theta)
            c = self.solve_linear(s, A, y - const)
            out.append(y - const - A @ c)
        return np.concatenate(out) if out else np.zeros(0)

    def sparsity(self):
        from scipy.sparse import lil_matrix
        n_rows = sum(x.size for x, _ in self.data)
        J = lil_matrix((n_rows, self.n_theta()), dtype=int)
        row = 0
        for s, (x, _) in enumerate(self.data):
            rows = slice(row, row + x.size)
            for c in range(len(self.shared)):
                J[rows, c] = 1
            for i in self.per_spectrum:
                J[rows, self._theta_index(s, i)] = 1
            row += x.size
        return J


def fit_global(spectra, template, share='positions', amplitude_constraints=None,
               background='auto', progress=None, manager=None):
    """Fit `spectra` together from the starting peaks `template` (see the
    module docstring). amplitude_constraints: one per spectrum ('positive'
    etc.). progress(evaluations, None) is called during the fit and may
    raise to stop it. Returns one result per spectrum (all failed: ok
    False)."""
    from scipy.optimize import least_squares
    manager = manager or PeakFittingManager()
    constraints = list(amplitude_constraints or ['unrestricted'] * len(spectra))
    failed = [{'label': str(s.get('label', '')), 'ok': False, 'peaks': None, 'r2': np.nan,
               'background': None, 'global': share} for s in spectra]
    if not template or len(spectra) < 1:
        return failed
    pr = _Problem(spectra, template, share, constraints, background, manager)
    if any(x.size <= 4 for x, _ in pr.data):
        return failed
    calls = [0]

    def fun(theta):
        calls[0] += 1
        if progress is not None and calls[0] % 5 == 0:
            progress(calls[0], None)
        return pr.residuals(theta)
    try:
        if pr.n_theta():
            fit = least_squares(fun, pr.theta0, bounds=(pr.lo, pr.hi), method='trf',
                                jac_sparsity=pr.sparsity(), x_scale='jac', max_nfev=400)
            theta = fit.x
        else:
            theta = np.zeros(0)
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        logger.error("Global peak fit failed: %s", exc)
        return failed
    return _results(pr, theta, spectra)


def _results(pr, theta, spectra):
    """The results of the fit: values, R², backgrounds and uncertainties."""
    designs, coefs, residuals = [], [], []
    for s, (x, y) in enumerate(pr.data):
        A, const, names, full = pr.design(s, theta)
        c = pr.solve_linear(s, A, y - const)
        designs.append((A, const, names, full))
        coefs.append(c)
        residuals.append(y - const - A @ c)
    n_obs = sum(r.size for r in residuals)
    n_par = pr.n_theta() + sum(c.size for c in coefs)
    ssr = float(sum(np.sum(r ** 2) for r in residuals))
    s2 = ssr / max(n_obs - n_par, 1)
    cov = _covariance(pr, theta, designs, coefs, s2)
    out = []
    p_index = np.cumsum([pr.n_theta()] + [c.size for c in coefs])
    for s, (x, y) in enumerate(pr.data):
        A, const, names, full = designs[s]
        c = coefs[s]
        full = _full_params(pr, s, theta, c, names)
        # the covariance of this spectrum's values: J (d values / d all) C J^T
        idx = list(range(pr.n_theta())) + list(range(p_index[s], p_index[s] + c.size))
        jac = np.zeros((pr.n_full, len(idx)))
        for col, g in enumerate(idx):
            if g < pr.n_theta():
                step = theta.copy()
                step[g] += 1.0
                jac[:, col] = _full_params(pr, s, step, c, names) - full
            else:
                step = c.copy()
                step[g - p_index[s]] += 1.0
                jac[:, col] = _full_params(pr, s, theta, step, names) - full
        sub = cov[np.ix_(idx, idx)] if cov is not None else np.full((len(idx),) * 2, np.inf)
        bad_cols = ~np.all(np.isfinite(sub), axis=0)
        cov_full = jac @ np.where(np.isfinite(sub), sub, 0.0) @ jac.T
        bad = np.any(jac[:, bad_cols] != 0, axis=1) if bad_cols.any() else np.zeros(pr.n_full,
                                                                                    bool)
        cov_full[bad, :] = np.inf
        cov_full[:, bad] = np.inf
        peaks = []
        for k, (model, n) in enumerate(pr.defs):
            i = pr.offset[k]
            params = full[i:i + n]
            peaks.append({'model': model,
                          'parameters': pr.m.get_peak_properties(model, params),
                          'errors': pr.m.peak_errors(model, params,
                                                     cov_full[i:i + n, i:i + n])})
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - float(np.sum(residuals[s] ** 2)) / ss_tot if ss_tot > 0 else np.nan
        bg = None
        kind = pr.bg_kind[s]
        if kind in ('constant', 'linear'):
            x0, x1 = pr.bg_range[s]
            cols = [k for k, nm in enumerate(names) if nm[0] == 'bg']
            vals = [float(c[k]) for k in cols]
            errs = []
            for k in cols:
                g = p_index[s] + k
                v = cov[g, g] if cov is not None else np.inf
                errs.append(float(np.sqrt(v)) if np.isfinite(v) and v >= 0 else None)
            y0 = vals[0]
            y1 = vals[1] if kind == 'linear' else vals[0]
            bg = {'kind': kind, 'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1,
                  'y0_err': errs[0], 'y1_err': errs[1] if kind == 'linear' else errs[0]}
        out.append({'label': pr.labels[s], 'ok': True, 'peaks': peaks, 'r2': r2,
                    'background': bg, 'global': pr.share})
    return out


def _full_params(pr, s, theta, c, names):
    """All values of spectrum s (template layout) from theta and its linear
    solution c."""
    full = pr.full_nonlinear(s, theta)
    heights = {i: float(c[k]) for k, (kind, i) in enumerate(names) if kind == 'h'}
    for j, (root, factor) in pr.height_root.items():
        base = heights.get(root, float(pr.start[root]))
        full[j] = factor * base
    return full


def _covariance(pr, theta, designs, coefs, s2):
    """s² (J^T J)^-1 of all values (theta, then each spectrum's linear
    ones), J assembled block by block (a spectrum's own values only change
    its own residuals)."""
    n_t = pr.n_theta()
    sizes = [c.size for c in coefs]
    P = n_t + sum(sizes)
    JTJ = np.zeros((P, P))
    start = n_t
    for s, (x, y) in enumerate(pr.data):
        A, const, names, full = designs[s]
        c = coefs[s]
        base = const + A @ c
        Jt = np.zeros((x.size, n_t))
        for g in range(n_t):
            h = 1e-6 * max(abs(theta[g]), 1e-3)
            step = theta.copy()
            step[g] += h
            A2, const2, _, _ = pr.design(s, step)
            Jt[:, g] = (const2 + A2 @ c - base) / h
        blk = slice(start, start + c.size)
        JTJ[:n_t, :n_t] += Jt.T @ Jt
        JTJ[:n_t, blk] += Jt.T @ A
        JTJ[blk, :n_t] += A.T @ Jt
        JTJ[blk, blk] += A.T @ A
        start += c.size
    try:
        if not np.all(np.isfinite(JTJ)) or np.linalg.cond(JTJ) > 1e14:
            raise np.linalg.LinAlgError("singular")
        return s2 * np.linalg.inv(JTJ)
    except np.linalg.LinAlgError:
        cov = np.full((P, P), np.inf)
        try:
            inv = np.linalg.pinv(JTJ)
            ok = np.diag(JTJ) > 0
            cov[np.ix_(ok, ok)] = s2 * inv[np.ix_(ok, ok)]
        except np.linalg.LinAlgError:
            pass
        return cov
