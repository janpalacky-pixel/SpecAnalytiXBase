"""Endmember unmixing (2D Map -> Map Type "Unmixing"): VCA, N-FINDR,
non-negative / sum-to-one abundances, fit error, suggested number of
endmembers (src/modules/visualization_analysis/endmember_unmixing.py)."""
import numpy as np
import pytest

from src.modules.visualization_analysis import endmember_unmixing as eu

X = np.linspace(600, 1800, 400)


def _g(c, w, a=1.0):
    return a * np.exp(-0.5 * ((X - c) / w) ** 2)


def _assert_pure_pixels(found, A):
    """Each found pixel is (almost) pure, one per substance (random
    mixtures also contain pixels 99 % pure besides the planted ones)."""
    shares = A[np.asarray(found)] / A[np.asarray(found)].sum(axis=1, keepdims=True)
    assert shares.max(axis=1).min() > 0.97
    assert sorted(shares.argmax(axis=1)) == [0, 1, 2]


def _truth():
    return np.vstack([_g(1003, 6) + _g(1450, 15, .6) + 0.2,
                      _g(1655, 12) + _g(1250, 20, .5) + 0.2,
                      _g(785, 8) + _g(1095, 8, .8) + 0.2])


def _data(n=900, noise=0.01, scale=True, seed=1):
    rng = np.random.default_rng(seed)
    E = _truth()
    A = rng.dirichlet(np.ones(3) * 0.7, n)
    pure = rng.choice(n, 3, replace=False)
    A[pure] = np.eye(3)
    s = rng.uniform(0.7, 1.3, n)[:, None] if scale else np.ones((n, 1))
    Y = (A * s) @ E + rng.normal(0, noise, (n, len(X)))
    return Y, E, A * s, pure


def _spectra(Y):
    return [{'label': f'p{i}', 'x_scale': X, 'y_scale': y} for i, y in enumerate(Y)]


@pytest.mark.parametrize('method', ['vca', 'nfindr'])
def test_finds_the_pure_pixels_and_their_spectra(method):
    Y, E, A, pure = _data()
    mgr = eu.EndmemberManager()
    assert mgr.compute(_spectra(Y), 3, method=method)
    _assert_pure_pixels(mgr.endmember_indices, A)
    corr = np.corrcoef(np.vstack([mgr.H, E]))[:3, 3:]
    assert corr.max(axis=1).min() > 0.99
    # the endmembers ARE measured spectra
    for k, i in enumerate(mgr.endmember_indices):
        assert np.array_equal(mgr.H[k], Y[i])
    assert mgr.W.shape == (len(Y), 3) and (mgr.W >= 0).all()
    assert mgr.lof < 8 and len(mgr.residual_rms) == len(Y)
    assert abs(mgr.explained_variance.sum() - 100) < 1e-9
    assert list(mgr.explained_variance) == sorted(mgr.explained_variance, reverse=True)


def test_abundances_recover_the_mixture():
    Y, E, A, _ = _data(noise=0.0)
    got = eu.abundances(Y, E)
    assert np.allclose(got, A, atol=1e-6)


def test_sum_to_one():
    Y, E, A, _ = _data(noise=0.0, scale=False)
    got = eu.abundances(Y, E, sum_to_one=True)
    assert np.allclose(got.sum(axis=1), 1, atol=1e-3)
    assert np.allclose(got, A, atol=1e-3) and (got >= 0).all()
    mgr = eu.EndmemberManager()
    assert mgr.compute(_spectra(Y), 3, sum_to_one=True)
    assert np.allclose(mgr.W.sum(axis=1), 1, atol=1e-3) and mgr.sum_to_one


def test_brightness_differences_do_not_fool_nfindr():
    Y, E, A, pure = _data(scale=True, seed=5)
    idx, sweeps = eu.nfindr(Y, 3, init=[0, 1, 2])      # bad start on purpose
    _assert_pure_pixels(idx, A)
    assert sweeps >= 1


def test_suggested_number_of_endmembers():
    Y, *_ = _data(noise=0.02)
    est = eu.estimate_n_endmembers(Y)
    assert est['n'] == 3
    assert est['sigma'] == pytest.approx(0.02, rel=0.25)
    assert est['singular_values'][2] > est['threshold'] > est['singular_values'][3]


def test_fit_error_shows_a_missing_component():
    Y, E, A, _ = _data(noise=0.005)
    extra = 0.5 * _g(1300, 10)
    Y[:50] += extra                           # a 4th substance in 50 pixels only
    mgr = eu.EndmemberManager()
    assert mgr.compute(_spectra(Y), 3)
    assert mgr.residual_rms[:50].mean() > 3 * mgr.residual_rms[50:].mean()


def test_errors_are_reported_not_raised():
    Y, *_ = _data(n=50)
    mgr = eu.EndmemberManager()
    assert not mgr.compute(_spectra(Y), 60)
    assert '60 endmembers' in mgr.last_error
    Y[3, 5] = np.nan
    assert not mgr.compute(_spectra(Y), 3)
    assert 'missing' in mgr.last_error
    assert not mgr.compute(_spectra(Y[:10]), 2, method='weird')
    assert not eu.EndmemberManager().compute([], 2)


def test_one_endmember_and_reproducible():
    Y, *_ = _data(n=200)
    mgr = eu.EndmemberManager()
    assert mgr.compute(_spectra(Y), 1)
    assert mgr.H.shape == (1, len(X))
    a, b = eu.EndmemberManager(), eu.EndmemberManager()
    a.compute(_spectra(Y), 3, random_state=4)
    b.compute(_spectra(Y), 3, random_state=4)
    assert np.array_equal(a.endmember_indices, b.endmember_indices)



def test_suggestion_holds_when_brighter_pixels_are_noisier():
    """Raman-like noise (larger in brighter pixels): the noise is read from
    the flat part of the singular-value curve itself."""
    rng = np.random.default_rng(2)
    E = _truth()
    A = rng.dirichlet(np.ones(3) * 0.7, 900) * rng.uniform(0.5, 2.0, (900, 1))
    clean = A @ E
    Y = clean + rng.normal(0, 1, clean.shape) * 0.03 * np.sqrt(clean)
    est = eu.estimate_n_endmembers(Y)
    assert est['n'] == 3 and est['clear'] == 3
    assert len(est['plateau']) == len(est['singular_values'])


def test_denoise_first():
    Y, E, A, pure = _data(noise=0.05, seed=3)
    noisy, clean = eu.EndmemberManager(), eu.EndmemberManager()
    assert noisy.compute(_spectra(Y), 3) and clean.compute(_spectra(Y), 3, denoise='auto')
    assert noisy.denoise_k is None and clean.denoise_k == 3 and clean.n_above_noise == 3
    # the denoised endmember spectra are much closer to the truth
    def err(mgr):
        corr = np.corrcoef(np.vstack([mgr.H, E]))[:3, 3:]
        return 1 - corr.max(axis=1).min()
    assert err(clean) < 0.5 * err(noisy)
    two = eu.EndmemberManager()
    assert two.compute(_spectra(Y), 3, denoise=2) and two.denoise_k == 3    # never below p
    Yd = eu.denoise(Y, 3)
    assert Yd.shape == Y.shape and np.linalg.matrix_rank(Yd) == 3
