"""Bugs found by the automatic bug hunt (every tool on awkward data, see
tests/test_smoke_all_tools.py). Each test failed before its fix."""
import numpy as np
import pytest

from src.modules.utils.spectrum_identity import spectrum_key


def _spectra(n=6, points=300, values=None, x=None):
    x = np.linspace(400, 1800, points) if x is None else x
    out = []
    for i in range(n):
        y = (5 * np.exp(-((x - 800 - 20 * i) / 15) ** 2) + 0.002 * x) if values is None else values(i, x)
        out.append({'label': f'set : s{i}', 'x_scale': x.copy(), 'y_scale': np.asarray(y, float),
                    'metadata': {'unique_id': f'u{i}'}})
    return out


# 1. Spectral Calculator silently produced NaN/inf, which broke later tools.
def test_calculator_refuses_undefined_results_and_says_where():
    from src.modules.data_analysis.spectral_calculator_manager import SpectralCalculatorManager
    cd_like = _spectra(values=lambda i, x: np.sin(x / 100.0))          # half negative
    a = cd_like[0]['label']
    with pytest.raises(ValueError, match='undefined at .* points'):
        SpectralCalculatorManager().evaluate(f'log({a})', cd_like)
    with pytest.raises(ValueError, match='division by zero'):
        SpectralCalculatorManager().evaluate(f'{a} / ({a} - {a})', cd_like)
    ok = SpectralCalculatorManager().evaluate(f'log(abs({a}) + 1e-6)', cd_like)
    assert np.isfinite(ok[0]['y_scale']).all()


# 2. SNIP crashed when the smoothing window was wider than the spectrum.
@pytest.mark.parametrize('points', [3, 5, 8])
def test_snip_smoothing_window_wider_than_short_spectrum(points):
    from src.modules.data_analysis.snip_baseline_manager import SNIPBaselineManager
    spectra = _spectra(n=2, points=points)
    out = SNIPBaselineManager().apply_correction(
        spectra, {'n_iter': 40, 'decreasing': False, 'smooth_window': 7, 'transform': False})
    assert [len(s['y_scale']) for s in out] == [points, points]
    assert all(np.isfinite(s['y_scale']).all() for s in out)


# 3. Automatic melting fit divided by zero on a perfectly flat curve.
def test_automatic_melting_fit_on_flat_curve_explains_instead_of_crashing():
    from src.modules.visualization_analysis.melting_curve_manager import MeltingCurveManager
    t = np.linspace(10, 90, 25)
    out = MeltingCurveManager().fit_automatic(t, np.full_like(t, 3.0))
    assert out['success'] is False
    assert 'flat' in out['reason']


# 4. NMF could fail without any reason for the dialog to show.
def test_nmf_failure_always_has_a_reason(monkeypatch):
    import sklearn.decomposition
    from src.modules.visualization_analysis.nmf_manager import NMFManager

    class _Broken:
        def __init__(self, *a, **k):
            raise RuntimeError('solver exploded')
    monkeypatch.setattr(sklearn.decomposition, 'NMF', _Broken)
    m = NMFManager()
    assert m.compute(_spectra(), 2) is False
    assert m.last_error and 'solver exploded' in m.last_error
    m2 = NMFManager()
    assert m2.compute([], 2) is False and m2.last_error


# 5. PLS on identical spectra showed a meaningless solver error.
def test_pls_on_identical_spectra_says_so():
    from src.modules.visualization_analysis.pls_manager import PLSManager
    same = _spectra(values=lambda i, x: np.exp(-((x - 900) / 20) ** 2))
    y = {spectrum_key(s): float(i) for i, s in enumerate(same)}
    with pytest.raises(ValueError, match='identical'):
        PLSManager().compute_pls(same, y)


# 6. Cosmic ray removal with one spectrum failed with a TypeError.
def test_cosmic_ray_removal_needs_two_spectra_clearly():
    from src.modules.data_analysis.cosmic_ray_manager import CosmicRayManager
    with pytest.raises(ValueError, match='at least 2 spectra'):
        CosmicRayManager().apply(_spectra(n=1))
