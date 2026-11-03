"""Peak Fitting: every fitted value has its uncertainty (standard error,
1 sigma) - from the fit's covariance, FWHM and area by error propagation. It
is shown in the Peaks table ("3365.77 ± 4.1"), copied with Copy Results and
listed in the Series results (a "±" column after each value)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QStyleOptionViewItem

from src.modules.data_analysis.peak_fitting_manager import (PeakFittingManager, gaussian, format_with_error,
                                                             format_error)
from src.modules.data_analysis import peak_fitting_series as pfs

app = QApplication.instance() or QApplication([])
X = np.linspace(0, 100, 501)
START = [{'model': 'Gaussian', 'center': 41.0, 'amplitude': 4.0, 'width': 3.0},
         {'model': 'Gaussian', 'center': 59.0, 'amplitude': 3.0, 'width': 5.0}]


def _data(seed, noise=0.2):
    rng = np.random.default_rng(seed)
    return gaussian(X, 5, 40, 3) + gaussian(X, 3, 60, 6) + 1.0 + rng.normal(0, noise, X.size)


def test_the_errors_match_the_scatter_of_repeated_fits():
    """60 noisy copies of the same spectrum: the standard deviation of the
    fitted values is what the errors of one fit say."""
    m = PeakFittingManager()
    keys = ('center', 'height', 'fwhm', 'area')
    values, errors = [], []
    for seed in range(60):
        fitted, _ = m.fit_peaks(X, _data(seed), START, background='linear')
        values.append([fitted[0]['parameters'][k] for k in keys])
        errors.append([fitted[0]['errors'][k] for k in keys])
    scatter = np.std(values, axis=0)
    mean_err = np.mean(errors, axis=0)
    assert np.allclose(mean_err, scatter, rtol=0.35)
    # the background has its own uncertainty too
    assert m.last_background['y0_err'] > 0 and m.last_background['y1_err'] > 0


def test_more_noise_larger_errors_and_every_model_has_them():
    m = PeakFittingManager()
    small, _ = m.fit_peaks(X, _data(1, noise=0.05), START, background='linear')
    large, _ = m.fit_peaks(X, _data(1, noise=0.5), START, background='linear')
    assert large[0]['errors']['center'] > 5 * small[0]['errors']['center']
    for model, extra in (('Lorentzian', None), ('Voigt', 'gamma'), ('Pseudo-Voigt', 'eta')):
        start = [dict(p, model=model, extra=0.5) for p in START]
        fitted, _ = m.fit_peaks(X, _data(2), start, background='linear')
        err = fitted[0]['errors']
        for key in ['center', 'height', 'fwhm', 'area', pfs.WIDTH_KEY[model]] + \
                [extra] * bool(extra):
            assert err[key] is not None and err[key] >= 0, (model, key)


def test_format_of_an_uncertainty():
    assert format_error(4.123) == '4.1'
    assert format_error(0.03214) == '0.032'
    assert format_error(123.4) == '123'
    assert format_error(0) == '0'
    assert format_error(None) == 'n/a' and format_error(float('nan')) == 'n/a'


def test_series_results_have_a_plus_minus_column_after_each_value():
    spectra = [{'label': f's{i}', 'x_scale': X, 'y_scale': _data(i)} for i in range(4)]
    for parallel in ({'processing_mode': 'serial'},
                     {'processing_mode': 'parallel', 'max_workers': 2}):
        results = pfs.fit_series_independent(spectra, START, background='linear',
                                             parallel=parallel)
        columns, rows = pfs.series_table(results, 2)
        assert columns[1:3] == ['Peak 1 position', 'Peak 1 position ±']
        assert all(0 < row[2] < 0.2 for row in rows)
    kept = pfs.plain(results)
    assert kept[0]['peaks'][0]['errors']['center'] == pytest.approx(rows[0][2], rel=1e-6)
    columns, rows = pfs.peaks_long(results, [0])
    assert columns[3:5] == ['Center', 'Center ±'] and rows[0][4] == pytest.approx(
        results[0]['peaks'][0]['errors']['center'])


@pytest.fixture
def fitted_dialog(monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    dlg = PeakFittingDialog(None, spectrum={'label': 'two bands', 'x_scale': X,
                                            'y_scale': _data(3), 'metadata': {}})
    dlg.peaks = [dict(p, color=c) for p, c in zip(START, ('#1f77b4', '#ff7f0e'))]
    dlg.update_peaks_table()
    dlg.perform_fit()
    return dlg


def _shown_text(table, row, col):
    option = QStyleOptionViewItem()
    index = table.model().index(row, col)
    table.itemDelegate().initStyleOption(option, index)
    return option.text


def test_peaks_table_shows_each_fitted_value_with_its_error(fitted_dialog):
    dlg = fitted_dialog
    t = dlg.peaks_table
    err = dlg.fit_results[0]['errors']['center']
    assert _shown_text(t, 0, 2) == format_with_error(float(t.item(0, 2).text()), err)
    assert _shown_text(t, 0, 2).endswith(f" ± {format_error(err)}")
    assert float(t.item(0, 2).text()) == pytest.approx(40, abs=0.1)   # the cell: the number
    assert '±' in _shown_text(t, 0, 3) and '±' in _shown_text(t, 0, 4)
    assert '±' not in _shown_text(t, 0, 5)                            # Gaussian: no Extra
    assert 'uncertainty' in t.item(0, 2).toolTip()
    assert all(len(line) <= 80 for line in t.item(0, 2).toolTip().split('\n'))   # short lines
    # edited (no longer the fit): the start values, without ±
    t.item(0, 2).setText('42.0')
    assert '±' not in _shown_text(t, 0, 2)


def test_copy_results_copies_the_errors_and_the_background(fitted_dialog):
    dlg = fitted_dialog
    dlg.copy_results_to_clipboard()
    lines = QApplication.clipboard().text().splitlines()
    assert lines[0].split('\t')[:5] == ['Peak', 'Model', 'Center', 'Center ±', 'Height']
    first = lines[1].split('\t')
    assert float(first[3]) == pytest.approx(dlg.fit_results[0]['errors']['center'], rel=1e-4)
    assert any(line.startswith('Background\tLinear') for line in lines)


def test_a_value_is_rounded_to_its_error():
    assert format_with_error(3431.5432, 3.123) == '3431.5 ± 3.1'
    assert format_with_error(11.4094, 0.2213) == '11.41 ± 0.22'
    assert format_with_error(412.6, 123.0) == '413 ± 123'
    assert format_with_error(5.0, None) == '5.0000 ± n/a'
