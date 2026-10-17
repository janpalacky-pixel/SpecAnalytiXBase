# src/modules/visualization_analysis/endmember_unmixing.py
"""Endmember unmixing of spectral maps (2D Map → Map Type "Unmixing").

Idea: in a map, some pixels are (almost) pure -- e.g. a pixel with nearly
only lipid, another with nearly only protein. Every other pixel is a mixture
of them. Endmember methods find those purest pixels; their measured spectra
are the *endmembers*. Then every pixel is explained as a non-negative
mixture of the endmembers: its *abundances*, one map per endmember.

Unlike NMF / MCR-ALS the endmembers are real measured spectra, not fitted
shapes, and the result does not depend on a starting guess in the same way.

* ``vca``  -- Vertex Component Analysis (Nascimento & Bioucas-Dias, 2005):
  repeatedly projects the data onto a direction orthogonal to the
  endmembers found so far and takes the most extreme pixel. Fast.
* ``nfindr`` -- N-FINDR (Winter, 1999): the endmembers are the pixels that
  span the simplex of largest volume (in the data reduced to p-1
  dimensions); improved by swapping one endmember at a time with every
  pixel until nothing grows. Started from the VCA result. Slower, more
  thorough -- a good cross-check.
* ``abundances`` -- non-negative least squares per pixel (NNLS), optionally
  with the abundances of every pixel summing to 1 (fully constrained,
  FCLS).
* ``estimate_n_endmembers`` -- how many components carry more than noise:
  singular values of the data above the largest singular value pure noise
  of the estimated level would give (sigma * (sqrt(N) + sqrt(L))).

``EndmemberManager`` exposes the same attributes NMFManager does (W = per-
pixel abundances, H = endmember spectra, x_axis, explained_variance, lof,
last_error), so the 2D Map handles it like its other decompositions.
"""
import math

import numpy as np
from scipy.optimize import nnls

METHODS = {'vca': 'VCA', 'nfindr': 'N-FINDR'}


# --------------------------------------------------------------------------- helpers

def _gram_eig(R):
    """Eigenvectors / eigenvalues of R R^T / N (L x L) for R of shape
    (L, N), largest first -- through the smaller of the two Gram matrices."""
    L, N = R.shape
    if L <= N:
        vals, vecs = np.linalg.eigh(R @ R.T / N)
        order = np.argsort(vals)[::-1]
        return vecs[:, order], vals[order]
    vals, vecs = np.linalg.eigh(R.T @ R / N)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    keep = vals > vals[0] * 1e-14 if vals[0] > 0 else np.zeros(len(vals), bool)
    U = R @ vecs[:, keep]
    U /= np.linalg.norm(U, axis=0, keepdims=True)
    full_vals = np.zeros(L)
    full_vals[:keep.sum()] = vals[keep]
    pad = np.zeros((L, L - U.shape[1]))
    return np.hstack([U, pad]), full_vals


def _check(Y, p):
    Y = np.asarray(Y, dtype=float)
    if Y.ndim != 2:
        raise ValueError("The data must be a matrix (pixels x points).")
    if not np.all(np.isfinite(Y)):
        raise ValueError("The spectra contain missing or infinite values.")
    n, L = Y.shape
    if p < 1:
        raise ValueError("At least 1 endmember is needed.")
    if p > min(n, L):
        raise ValueError(f"{p} endmembers need at least {p} pixels and {p} data points.")
    return Y


# --------------------------------------------------------------------------- VCA

def vca(Y, p, seed=0):
    """Vertex Component Analysis. Y: (n_pixels, n_points). Returns the
    pixel indices of the p endmembers (in the order found)."""
    Y = _check(Y, p)
    if p == 1:                                 # one endmember: the strongest pixel
        return np.array([int(np.argmax(np.linalg.norm(Y, axis=1)))])
    R = Y.T                                   # L x N, as in the paper
    L, N = R.shape
    rng = np.random.default_rng(seed)
    r_m = R.mean(axis=1, keepdims=True)
    R_m = R - r_m
    Ud, _ = _gram_eig(R_m)
    Ud = Ud[:, :p]
    x_p = Ud.T @ R_m
    # signal-to-noise estimate (decides the projection, as in the paper)
    P_y = np.sum(R ** 2) / N
    P_x = np.sum(x_p ** 2) / N + float(np.sum(r_m ** 2))
    denom = P_y - P_x
    snr = (10 * math.log10(max((P_x - p / L * P_y), 1e-300) / denom)
           if denom > 0 else np.inf)
    snr_th = 15 + 10 * math.log10(p)
    y = None
    if snr >= snr_th:
        Ud2, _ = _gram_eig(R)
        Ud2 = Ud2[:, :p]
        x = Ud2.T @ R
        u = x.mean(axis=1, keepdims=True)
        scale = np.sum(x * u, axis=0)
        if np.all(scale > 1e-12 * np.max(np.abs(scale))):
            y = x / scale                      # projective projection
    if y is None:                              # low SNR (or projection not possible)
        x = x_p[:p - 1]
        c = float(np.max(np.linalg.norm(x, axis=0))) or 1.0
        y = np.vstack([x, np.full((1, N), c)])
    indices = np.zeros(p, dtype=int)
    A = np.zeros((p, p))
    A[-1, 0] = 1.0
    for i in range(p):
        w = rng.random((p, 1))
        f = w - A @ np.linalg.pinv(A) @ w
        nf = np.linalg.norm(f)
        if nf < 1e-14:
            f = rng.standard_normal((p, 1))
            nf = np.linalg.norm(f)
        f /= nf
        v = (f.T @ y).ravel()
        v[indices[:i]] = 0                    # never the same pixel twice
        indices[i] = int(np.argmax(np.abs(v)))
        A[:, i] = y[:, indices[i]]
    return indices


# --------------------------------------------------------------------------- N-FINDR

def _reduce(Y, p):
    """The data reduced to p-1 dimensions (principal components of the
    mean-centred data), shape (n_pixels, p-1)."""
    Yc = Y - Y.mean(axis=0, keepdims=True)
    U, _ = _gram_eig(Yc.T)
    return Yc @ U[:, :max(p - 1, 0)]


def _simplex_matrix(Z, idx):
    return np.vstack([np.ones(len(idx)), Z[idx].T])     # p x p


def simplex_volume(Z, idx):
    """|det| of [1; z_i] for the chosen pixels -- proportional to the volume
    of the simplex they span (Z already reduced to p-1 dimensions)."""
    return abs(float(np.linalg.det(_simplex_matrix(Z, idx))))


def nfindr(Y, p, seed=0, max_sweeps=20, init=None):
    """N-FINDR: the p pixels spanning the largest simplex. Started from
    ``init`` (pixel indices; default: the VCA result). Returns (indices,
    number of sweeps)."""
    Y = _check(Y, p)
    if p == 1:
        return vca(Y, 1, seed), 0
    # brightness differences (focus, laser power) would make the brightest
    # mixtures look "extreme": compare the spectra's shapes (each pixel
    # divided by its sum), as VCA's projective projection does
    sums = Y.sum(axis=1, keepdims=True)
    Ys = Y / sums if np.all(sums > 1e-12 * np.max(np.abs(sums))) else Y
    Z = _reduce(Ys, p)
    idx = np.array(init if init is not None else vca(Y, p, seed), dtype=int)
    V = np.hstack([np.ones((len(Z), 1)), Z])           # rows [1, z_j]
    sweeps = 0
    for sweeps in range(1, max_sweeps + 1):
        changed = False
        for i in range(p):
            M = _simplex_matrix(Z, idx)
            # determinant with column i replaced by v = cof . v (cofactors of column i)
            cof = np.empty(p)
            for k in range(p):
                minor = np.delete(np.delete(M, k, axis=0), i, axis=1)
                cof[k] = (-1) ** (k + i) * np.linalg.det(minor)
            vols = np.abs(V @ cof)
            current = vols[idx[i]]
            others = np.delete(idx, i)
            vols[others] = -1                         # keep endmembers distinct
            best = int(np.argmax(vols))
            if vols[best] > current * (1 + 1e-9) and best != idx[i]:
                idx[i] = best
                changed = True
        if not changed:
            break
    return idx, sweeps


# --------------------------------------------------------------------------- abundances

def abundances(Y, E, sum_to_one=False):
    """Non-negative abundances A (n_pixels, p) with Y ~ A @ E.
    Y: (n_pixels, n_points), E: (p, n_points). sum_to_one: every row of A
    adds up to 1 (fully constrained least squares)."""
    Y = np.asarray(Y, dtype=float)
    E = np.asarray(E, dtype=float)
    G = E @ E.T                                   # p x p
    B = E @ Y.T                                   # p x n
    p = len(G)
    scale = float(np.mean(np.diag(G))) or 1.0
    G = G + np.eye(p) * scale * 1e-10             # identical endmembers: still solvable
    if sum_to_one:
        lam = 1e4 * scale
        G = G + lam * np.ones((p, p))
        B = B + lam
    C = np.linalg.cholesky(G)                    # G = C C^T
    rhs = np.linalg.solve(C, B)                  # p x n
    Ct = C.T
    A = np.empty((Y.shape[0], p))
    for j in range(Y.shape[0]):
        A[j], _ = nnls(Ct, rhs[:, j])
    return A


# --------------------------------------------------------------------------- number of endmembers

NOISE_FACTOR = 1.15     # a component counts as signal above 1.15 x the noise plateau
CLEAR_FACTOR = 2.0      # ... and as clearly signal above 2 x the noise plateau


def svd_basis(Y):
    """Singular values (largest first) and the matching spectral directions
    V (n_points x m) of Y (n_pixels x n_points), m = min(n_pixels, n_points)."""
    Y = np.asarray(Y, dtype=float)
    N, L = Y.shape
    m = min(N, L)
    if L <= N:
        vals, V = np.linalg.eigh(Y.T @ Y)
        order = np.argsort(vals)[::-1][:m]
        vals, V = vals[order], V[:, order]
    else:
        vals, U = np.linalg.eigh(Y @ Y.T)
        order = np.argsort(vals)[::-1][:m]
        vals, U = vals[order], U[:, order]
        s = np.sqrt(np.clip(vals, 0, None))
        keep = s > (s[0] * 1e-12 if s[0] > 0 else 0)
        V = np.zeros((L, m))
        V[:, keep] = (Y.T @ U[:, keep]) / s[keep]
    return np.sqrt(np.clip(vals, 0, None)), V


def noise_plateau(s, factor=NOISE_FACTOR):
    """The noise floor of the singular values: a straight line (log scale)
    fitted to the flat middle part of the curve (5 %..50 % of the
    components, which is noise in spectral maps), extended to the first
    components. Read from the data's own curve, so it also holds when the
    noise differs from pixel to pixel (Raman: brighter pixels are noisier).
    Returns (number of leading components above factor x plateau,
    plateau values)."""
    s = np.asarray(s, dtype=float)
    m = len(s)
    k = np.arange(m)
    k0 = max(4, int(0.05 * m))
    k1 = max(k0 + 4, int(0.5 * m))
    ls = np.log(np.clip(s, 1e-300, None))
    slope, offset = np.polyfit(k[k0:k1], ls[k0:k1], 1)
    plateau = np.exp(offset + slope * k)
    n = 0
    while n < m and s[n] > factor * plateau[n]:
        n += 1
    return n, plateau


def clear_count(s, plateau, n_above, factor=None):
    """Components CLEARLY above the noise: the leading singular values more
    than CLEAR_FACTOR (2) x the noise plateau. A component at 2 x the noise
    carries at least three quarters signal (1 - 1/2^2 of its squared size).
    Counted from the first component, at most n_above, at least 1 -- a
    practical number of substances to start with."""
    factor = CLEAR_FACTOR if factor is None else factor
    s = np.asarray(s, dtype=float)
    plateau = np.asarray(plateau, dtype=float)
    k = 0
    while k < min(len(s), len(plateau)) and s[k] > factor * plateau[k]:
        k += 1
    return max(1, min(k, max(n_above, 1)))


def estimate_n_endmembers(Y, max_n=50, s=None):
    """How many components carry more than noise.

    'n'     -- components above the noise (more than NOISE_FACTOR = 1.15 x
               the noise plateau, see noise_plateau): an upper limit for the
               number of substances;
    'clear' -- components clearly above the noise (more than CLEAR_FACTOR =
               2 x the plateau, see clear_count): a practical number to
               start with;
    plus 'singular_values', 'plateau', 'threshold' (factor x plateau at the
    first noise component) and 'sigma' (noise level from the second
    differences along the spectra, for information).
    With fewer than 12 singular values the classic limit for pure noise,
    1.2 sigma (sqrt(N) + sqrt(L)), is used instead of the plateau."""
    Y = np.asarray(Y, dtype=float)
    N, L = Y.shape
    if L >= 5:
        d2 = np.diff(Y, n=2, axis=1).ravel()
        mad = np.median(np.abs(d2 - np.median(d2)))
        sigma = 1.4826 * mad / math.sqrt(6.0)
    else:
        sigma = 0.0
    if s is None:
        s, _ = svd_basis(Y)
    s = np.asarray(s, dtype=float)
    if len(s) >= 12:
        n, plateau = noise_plateau(s)
        threshold = NOISE_FACTOR * plateau[min(n, len(s) - 1)]
    else:
        threshold = 1.2 * sigma * (math.sqrt(N) + math.sqrt(L))
        plateau = np.full(len(s), threshold / NOISE_FACTOR)
        n = int(np.sum(s > threshold)) if sigma > 0 else len(s)
    n = max(1, min(n, max_n))
    clear = clear_count(s, plateau, n)
    return {'n': n, 'clear': clear, 'sigma': sigma, 'threshold': threshold,
            'plateau': plateau, 'singular_values': s}


def denoise(Y, k, V=None):
    """Y with only its first k SVD components kept (the rest -- mostly noise
    -- removed): Y V_k V_k^T. V: the spectral directions from svd_basis()."""
    Y = np.asarray(Y, dtype=float)
    if V is None:
        _, V = svd_basis(Y)
    Vk = V[:, :max(1, int(k))]
    return (Y @ Vk) @ Vk.T


# --------------------------------------------------------------------------- manager

class EndmemberManager:
    """Endmember unmixing with the NMFManager-like interface the 2D Map
    uses: W (n_pixels x p abundances), H (p x n_points endmember spectra),
    x_axis, labels, explained_variance (% share of the modelled signal,
    as for NMF), lof (% lack of fit), last_error. Extra: endmember_indices
    (pixel of each endmember), residual_rms (per pixel), method,
    sum_to_one, sweeps (N-FINDR)."""

    def __init__(self):
        self.W = None
        self.H = None
        self.x_axis = None
        self.labels = []
        self.n_components = None
        self.explained_variance = None
        self.lof = None
        self.iterations_used = None
        self.converged = True
        self.last_error = None
        self.endmember_indices = None
        self.residual_rms = None
        self.method = 'vca'
        self.sum_to_one = False
        self.sweeps = None
        self.bootstrap_result = None
        self.denoise_k = None          # SVD components kept (None: not denoised)
        self.n_above_noise = None      # with denoise='auto': the estimate used

    def compute(self, spectra, n_components, method='vca', sum_to_one=False,
                random_state=0, denoise=None):
        """spectra: dicts with a common x-axis (already range-filtered).
        denoise: None (off), 'auto' (keep the components above the noise,
        see estimate_n_endmembers) or a number of SVD components to keep --
        the spectra are then cleaned that way first: the endmembers are the
        denoised spectra of the purest pixels, and lack of fit / fit error
        refer to the denoised spectra.
        Returns True on success, else False with last_error set."""
        self.last_error = None
        try:
            if not spectra:
                raise ValueError("No spectra.")
            x = np.asarray(spectra[0]['x_scale'], dtype=float)
            Y = np.vstack([np.asarray(s['y_scale'], dtype=float) for s in spectra])
            if Y.shape[1] != len(x):
                raise ValueError("The spectra do not share one x-axis.")
            p = int(n_components)
            Y = _check(Y, p)
            self.denoise_k = None
            self.n_above_noise = None
            if denoise:
                s_vals, V = svd_basis(Y)
                if denoise == 'auto':
                    est = estimate_n_endmembers(Y, s=s_vals)
                    self.n_above_noise = est['n']
                    k = est['n']
                else:
                    k = int(denoise)
                k = max(k, p)                   # p endmembers need p dimensions
                Y = (Y @ V[:, :k]) @ V[:, :k].T
                self.denoise_k = k
            if method == 'nfindr':
                idx, self.sweeps = nfindr(Y, p, seed=random_state)
            elif method == 'vca':
                idx, self.sweeps = vca(Y, p, seed=random_state), None
            else:
                raise ValueError(f"Unknown method {method!r}.")
            if len(set(int(i) for i in idx)) < p:
                raise ValueError("Fewer distinct endmember pixels were found than "
                                 "requested -- try fewer endmembers.")
            E = Y[idx]
            A = abundances(Y, E, sum_to_one=sum_to_one)
        except ValueError as exc:
            self.last_error = str(exc)
            return False
        except np.linalg.LinAlgError as exc:
            self.last_error = f"The calculation failed ({exc}); try fewer endmembers."
            return False
        residual = Y - A @ E
        comp_ss = np.sum(A ** 2, axis=0) * np.sum(E ** 2, axis=1)
        total = comp_ss.sum()
        ev = 100.0 * comp_ss / total if total > 0 else np.zeros(p)
        order = np.argsort(-ev, kind='stable')
        self.W = A[:, order]
        self.H = E[order]
        self.endmember_indices = np.asarray(idx)[order]
        self.explained_variance = ev[order]
        self.x_axis = x
        self.labels = [s.get('label', '') for s in spectra]
        self.n_components = p
        norm = np.linalg.norm(Y)
        self.lof = 100.0 * np.linalg.norm(residual) / norm if norm > 0 else 0.0
        self.residual_rms = np.sqrt(np.mean(residual ** 2, axis=1))
        self.method = method
        self.sum_to_one = bool(sum_to_one)
        return True
