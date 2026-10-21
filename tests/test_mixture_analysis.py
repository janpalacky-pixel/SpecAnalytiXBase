"""Analysis & Visualization -> Data Analysis -> Mixture analysis (known
components): each spectrum as a sum of known component spectra (classical
least squares), optionally non-negative and with a background."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis import mixture_analysis as ma

app = QApplication.instance() or QApplication([])

X = np.linspace(400, 700, 301)
G = lambda c, w, x=X: np.exp(-((x - c) / w) ** 2)
A = {'label': 'pure A', 'x_scale': X, 'y_scale': G(500, 20)}
B = {'label': 'pure B', 'x_scale': X, 'y_scale': G(560, 30)}


def _mix(a, b, offset=0.0, slope=0.0, label='mix', x=X):
    return {'label': label, 'x_scale': x, 'y_scale': a * G(500, 20, x) + b * G(560, 30, x)
            + offset + slope * (x - 550)}


def test_known_amounts_are_found():
    f = ma.fit_mixture(_mix(0.3, 0.7), [A, B])
    assert np.allclose(f.amounts, [0.3, 0.7], atol=1e-6) and f.r2 == pytest.approx(1)
    assert np.allclose(f.fractions, [0.3, 0.7])
    assert np.allclose(f.parts[0] + f.parts[1], f.fit)


def test_background_constant_and_slope():
    f = ma.fit_mixture(_mix(0.3, 0.7, offset=0.1, slope=0.0005), [A, B], background='linear')
    assert np.allclose(f.amounts, [0.3, 0.7], atol=1e-6)
    assert np.allclose(f.background, [0.1, 0.0005], atol=1e-6)    # middle of the range, per x unit
    plain = ma.fit_mixture(_mix(0.3, 0.7, offset=0.1, slope=0.0005), [A, B])
    assert plain.r2 < 0.99                                        # without it, it does not fit


def test_never_negative_and_plain_least_squares():
    y = _mix(0.5, 0.0)
    y['y_scale'] = y['y_scale'] - 0.05 * G(560, 30)                 # "a little less than none of B"
    nn = ma.fit_mixture(y, [A, B], nonnegative=True)
    ls = ma.fit_mixture(y, [A, B], nonnegative=False)
    assert nn.amounts[1] == 0 and ls.amounts[1] == pytest.approx(-0.05, abs=1e-6)


def test_different_x_axes_and_the_x_range():
    x2 = np.linspace(450, 650, 151)[::-1]                          # other points, descending
    f = ma.fit_mixture(_mix(0.4, 0.2, x=x2), [A, B])
    assert np.allclose(f.amounts, [0.4, 0.2], atol=1e-3)
    f = ma.fit_mixture(_mix(0.4, 0.2), [A, B], x_range=(480, 520))  # only A's band
    assert f.x.min() >= 480 and f.x.max() <= 520
    bad = ma.fit_mixture({'label': 'far', 'x_scale': np.linspace(800, 900, 50),
                          'y_scale': np.ones(50)}, [A, B])
    assert bad.error and np.isnan(bad.amounts).all()


def test_table_copy_and_export(tmp_path):
    fits = ma.analyse([_mix(0.3, 0.7, 0.1, label='s1'), _mix(0.6, 0.1, 0.1, label='s2')], [A, B],
                      background='constant')
    cols = ma.table_columns(['pure A', 'pure B'], 'constant')
    rows = ma.table_rows(fits, 'constant')
    assert cols == ['Spectrum', 'Amount of pure A', 'Amount of pure B', 'Fraction of pure A',
                    'Fraction of pure B', 'Background (constant)', 'R²', 'Residual (RMS)']
    assert rows[1][0] == 's2' and rows[1][1] == pytest.approx(0.6, abs=1e-6)
    assert ma.rows_as_text(cols, rows).splitlines()[0].split('\t') == cols
    import pandas as pd
    ma.export(cols, rows, str(tmp_path / 'm.xlsx'))
    assert pd.read_excel(tmp_path / 'm.xlsx').shape == (2, len(cols))


def test_the_window(monkeypatch):
    from src.views.dialogs.data_analysis.mixture_analysis_dialog import MixtureAnalysisDialog
    dlg = MixtureAnalysisDialog(None, [A, B, _mix(0.3, 0.7, label='s1'), _mix(0.2, 0.2, label='s2')])
    assert dlg.calculate() is None and 'Tick' in dlg.message.text()
    dlg.set_components({'pure A', 'pure B', 's1', 's2'})
    assert dlg.calculate() is None and 'unticked' in dlg.message.text()
    dlg.set_components({'pure A', 'pure B'})
    fits = dlg.calculate()
    assert [f.label for f in fits] == ['s1', 's2'] and dlg.table.rowCount() == 2
    assert dlg.table.item(0, 1).text() == '0.3' and 'R²' in dlg.message.text()
    assert len(dlg.figure.axes) == 2                               # spectrum + residual
    dlg.table.selectRow(1)
    dlg.copy()
    assert QApplication.clipboard().text().splitlines()[1].startswith('s2\t')


def test_menu_entry(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.views.dialogs.data_analysis import mixture_analysis_dialog as mad
    shown = []
    monkeypatch.setattr(mad.MixtureAnalysisDialog, 'exec_', lambda self: shown.append(self) or 0)
    mc = MainController()
    try:
        mc.original_spectra = [A, B, _mix(0.3, 0.7)]
        mc.selected_spectra = list(mc.original_spectra)
        mc.spectrum_selector.get_selected_spectra = lambda: list(mc.original_spectra)
        mc.view.actionMenuMixtureAnalysis.trigger()
        assert shown and shown[0].list.count() == 3
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
