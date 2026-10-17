"""How many components carry signal -- shared by SVD Analysis, the 2D Map's
SVD diagnostics, PCA Scores & Loadings, SVD background correction and SVD
interpolation (one formula everywhere).

The data table has n_pts spectral points and n_sp spectra. Its singular
values s are the same whichever way round the table is written, but two of
the criteria below depend on which side is which:

* Malinowski's IND (1977) is defined for a table with r rows and c columns
  where c <= r: c is the SMALLER side (the most components there can be),
  r the LARGER one. For a few spectra with many points (a temperature
  series) c = number of spectra; for a 2D map (21 000 spectra of 1 600
  points) c = number of points. Taking c = number of spectra for a map
  makes IND keep falling to the very last component -- a meaningless
  "optimum".
* The residual error E(m) uses (n_pts - m)(n_sp - m) and is the same either
  way -- but it needs the real numbers of points and spectra, not the size
  of U (for a map U has as many columns as points, not spectra).

The noise plateau (see endmember_unmixing.noise_plateau) reads the noise
level from the flat end of the singular-value curve; it is the criterion
behind Unmixing -> Suggest number.

Reference: Malinowski, E.R. (1977) Anal. Chem. 49, 612-617; Malinowski,
E.R. (2002) Factor Analysis in Chemistry, 3rd ed., Wiley."""
import numpy as np

from src.modules.visualization_analysis.endmember_unmixing import (
    CLEAR_FACTOR, NOISE_FACTOR, clear_count, noise_plateau)

MIN_VALUES_FOR_PLATEAU = 12


def table_sides(n_pts, n_sp):
    """(r, c): the larger and the smaller side of the data table."""
    n_pts, n_sp = int(n_pts), int(n_sp)
    return max(n_pts, n_sp), min(n_pts, n_sp)


def residual_error(s, n_pts, n_sp):
    """E(m) for m = 1 .. k-1 components kept (index m-1):
    sqrt( sum_{j>m} s_j^2 / ((n_pts - m)(n_sp - m)) ). s must be ALL the
    singular values (not only the first few), else the sum is too small."""
    s = np.asarray(s, dtype=float)
    k = len(s)
    if k < 2 or n_sp < 2:
        return np.zeros(max(k - 1, 1))
    lam = s ** 2
    rest = np.cumsum(lam[::-1])[::-1]            # rest[j] = sum lam[j:]
    out = np.zeros(k - 1)
    for m in range(1, k):
        den = (n_pts - m) * (n_sp - m)
        out[m - 1] = np.sqrt(rest[m] / den) if den > 0 else 0.0
    return out


def malinowski_ind(s, n_pts, n_sp):
    """Malinowski's indicator function IND(n) for n = 1 .. k-1 components
    (index n-1): RE(n) / (c - n)^2 with RE(n) = sqrt( sum_{j>n} s_j^2 /
    (r (c - n)) ), r / c the larger / smaller side of the table (see the
    module docstring). Its minimum is the suggested number of components.
    NaN where it is not defined (n >= c)."""
    s = np.asarray(s, dtype=float)
    k = len(s)
    out = np.full(max(k - 1, 0), np.nan)
    r, c = table_sides(n_pts, n_sp)
    if k < 2 or c < 2:
        return out
    lam = s ** 2
    rest = np.cumsum(lam[::-1])[::-1]
    for n in range(1, k):
        if n >= c:
            break
        re = np.sqrt(rest[n] / (r * (c - n)))
        out[n - 1] = re / (c - n) ** 2
    return out


def ind_minimum(ind):
    """Number of components at the IND minimum (1-based), or None."""
    ind = np.asarray(ind, dtype=float)
    if ind.size == 0 or not np.any(np.isfinite(ind)):
        return None
    return int(np.nanargmin(ind)) + 1


def noise_limit(s):
    """The noise plateau of the singular values, the number of components
    above it (more than NOISE_FACTOR x plateau) and clearly above it (more
    than CLEAR_FACTOR x plateau) --
    the same numbers as Unmixing -> Suggest number. None with fewer than
    MIN_VALUES_FOR_PLATEAU values (too few to see a flat part)."""
    s = np.asarray(s, dtype=float)
    if len(s) < MIN_VALUES_FOR_PLATEAU or not np.all(np.isfinite(s)) or s[0] <= 0:
        return None
    n, plateau = noise_plateau(s)
    n = max(1, n)
    clear = clear_count(s, plateau, n)
    return {'n': n, 'clear': clear, 'plateau': plateau, 'factor': NOISE_FACTOR,
            'clear_factor': CLEAR_FACTOR}


GRAM_MIN_SIZE = 400


def _top_eigh(G, k):
    """Eigenvalues / vectors of the symmetric G: only the k largest when k
    is small compared with its size (LAPACK computes just those -- several
    times faster than all of them), otherwise all."""
    m = G.shape[0]
    if k < m // 4:
        try:
            import scipy.linalg
            return scipy.linalg.eigh(G, subset_by_index=[m - k, m - 1], driver='evx')
        except Exception:
            pass
    return np.linalg.eigh(G)


def leading_svd(X, k):
    """The first k singular triplets of X: (U[:, :k], s[:k], Vt[:k, :]), as
    np.linalg.svd(X, full_matrices=False) would give them (up to the sign
    of each component).

    For a large table (both sides >= GRAM_MIN_SIZE) the eigen-decomposition
    of the smaller Gram matrix is used: about 4 x faster than the full SVD
    for 1 600 x 3 000 (used by the SVD / PCA bootstrap, which repeats it for
    every replicate). Its precision for component j is ~ machine precision
    x (s_1 / s_j)^2, so if the k-th value is very small compared with the
    first, the full SVD is used instead."""
    X = np.asarray(X, dtype=float)
    n_r, n_c = X.shape
    k = int(min(k, n_r, n_c))
    if min(n_r, n_c) >= GRAM_MIN_SIZE:
        if n_c <= n_r:
            w, V = _top_eigh(X.T @ X, k)
            order = np.argsort(w)[::-1][:k]
            s = np.sqrt(np.clip(w[order], 0, None))
            if s[0] > 0 and s[-1] > 1e-4 * s[0]:
                V = V[:, order]
                return (X @ V) / s, s, V.T
        else:
            w, U = _top_eigh(X @ X.T, k)
            order = np.argsort(w)[::-1][:k]
            s = np.sqrt(np.clip(w[order], 0, None))
            if s[0] > 0 and s[-1] > 1e-4 * s[0]:
                U = U[:, order]
                return U, s, (U.T @ X) / s[:, None]
    U, s, Vt = np.linalg.svd(X, full_matrices=False)
    return U[:, :k], s[:k], Vt[:k, :]
