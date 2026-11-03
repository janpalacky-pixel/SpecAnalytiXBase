"""Peak Fitting: a value can be fixed (kept, not fitted) or linked to another
peak - the same width, a fixed distance between centres, a fixed height
ratio. Right-click on a value in the table of peaks."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QStyleOptionViewItem

from src.modules.data_analysis.peak_fitting_manager import PeakFittingManager, gaussian
from src.modules.data_analysis import peak_fitting_series as pfs

app = QApplication.instance() or QApplication([])
X = np.linspace(0, 100, 501)


def _data(seed=0):
    rng = np.random.default_rng(seed)
    return (gaussian(X, 5, 40, 3) + gaussian(X, 2.5, 52, 3) + gaussian(X, 1.2, 70, 3)
            + rng.normal(0, 0.1, X.size))


def _start():
    return [{'id': 'p1', 'model': 'Gaussian', 'center': 41.0, 'amplitude': 4.0, 'width': 3.5},
            {'id': 'p2', 'model': 'Gaussian', 'center': 51.0, 'amplitude': 2.0, 'width': 2.5},
            {'id': 'p3', 'model': 'Gaussian', 'center': 70.5, 'amplitude': 1.0, 'width': 3.0}]


def _fit(start, **kw):
    m = PeakFittingManager()
    fitted, total = m.fit_peaks(X, _data(), start, **kw)
    assert fitted is not None
    return fitted


def test_a_fixed_value_stays_and_has_no_uncertainty():
    start = _start()
    start[2]['constraints'] = {'center': {'kind': 'fixed'}}
    fitted = _fit(start)
    assert fitted[2]['parameters']['center'] == 70.5
    assert fitted[2]['errors']['center'] == 0
    assert fitted[2]['errors']['height'] > 0                     # the rest is fitted


def test_the_same_width_distance_and_ratio():
    start = _start()
    start[1]['constraints'] = {'width': {'kind': 'link', 'peak': 'p1'},
                               'center': {'kind': 'link', 'peak': 'p1', 'value': 12.0},
                               'height': {'kind': 'link', 'peak': 'p1', 'value': 0.5}}
    start[2]['constraints'] = {'width': {'kind': 'link', 'peak': 'p1'}}
    p = [f['parameters'] for f in _fit(start)]
    assert p[1]['sigma'] == pytest.approx(p[0]['sigma']) == pytest.approx(p[2]['sigma'])
    assert p[1]['center'] - p[0]['center'] == pytest.approx(12.0)
    assert p[1]['height'] / p[0]['height'] == pytest.approx(0.5)
    assert p[0]['sigma'] == pytest.approx(3.0, abs=0.05)


def test_a_linked_value_gets_the_uncertainty_of_its_peak():
    start = _start()
    start[1]['constraints'] = {'width': {'kind': 'link', 'peak': 'p1'}}
    fitted = _fit(start)
    assert fitted[1]['errors']['sigma'] == pytest.approx(fitted[0]['errors']['sigma'])
    # one shared width is better determined than two separate ones
    free = _fit(_start())
    assert fitted[0]['errors']['sigma'] < free[0]['errors']['sigma']


def test_links_that_cannot_work_are_fitted_freely():
    start = _start()
    start[0]['constraints'] = {'width': {'kind': 'link', 'peak': 'p2'}}       # a circle
    start[1]['constraints'] = {'width': {'kind': 'link', 'peak': 'p1'},
                               'center': {'kind': 'link', 'peak': 'gone', 'value': 1}}
    start[2]['model'] = 'Lorentzian'                      # a width of another shape
    start[2]['constraints'] = {'width': {'kind': 'link', 'peak': 'p1'}}
    fitted = _fit(start)
    assert fitted[1]['parameters']['center'] == pytest.approx(52, abs=0.1)


def test_everything_fixed_gives_the_curve_without_a_fit():
    start = _start()
    for p in start:
        p['constraints'] = {k: {'kind': 'fixed'} for k in ('height', 'center', 'width')}
    fitted = _fit(start)
    assert [f['parameters']['center'] for f in fitted] == [41.0, 51.0, 70.5]


def test_series_fits_keep_the_links():
    spectra = [{'label': f's{i}', 'x_scale': X, 'y_scale': _data(i)} for i in range(4)]
    start = _start()
    start[1]['constraints'] = {'width': {'kind': 'link', 'peak': 'p1'}}
    for parallel in ({'processing_mode': 'serial'},
                     {'processing_mode': 'parallel', 'max_workers': 2}):
        results = pfs.fit_series_independent(spectra, start, parallel=parallel)
        for r in results:
            assert r['peaks'][1]['parameters']['sigma'] == pytest.approx(
                r['peaks'][0]['parameters']['sigma'])
    results = pfs.fit_series(spectra, start)                 # each from the fit before
    assert all(r['peaks'][1]['parameters']['sigma'] == pytest.approx(
        r['peaks'][0]['parameters']['sigma']) for r in results)


# ---------------------------------------------------------------- the window
@pytest.fixture
def dlg(monkeypatch):
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: None))
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    d = PeakFittingDialog(None, spectrum={'label': 'three bands', 'x_scale': X,
                                          'y_scale': _data(), 'metadata': {}})
    d.peaks = [dict(p, color=c) for p, c in zip(_start(), ('#1f77b4', '#ff7f0e', '#2ca02c'))]
    for p in d.peaks:
        p.pop('id')                                   # the window gives the ids
    d.update_peaks_table()
    return d


def _shown(table, row, col):
    option = QStyleOptionViewItem()
    table.itemDelegate().initStyleOption(option, table.model().index(row, col))
    return option.text


def test_right_click_menu_fixes_and_links(dlg):
    menu = dlg.peaks_constraint_menu(dlg.peaks_table.model().index(2, 2))      # Center of P3
    texts = [a.text() for a in menu.actions()]
    assert texts[0] == 'Center of peak 3'
    fixed = [a for a in menu.actions() if a.text().startswith('Fixed')][0]
    fixed.trigger()
    assert dlg.peaks[2]['constraints']['center'] == {'kind': 'fixed'}
    assert _shown(dlg.peaks_table, 2, 2).startswith('[fixed] 70.5')
    # Width of peak 2: the same as peak 1
    menu = dlg.peaks_constraint_menu(dlg.peaks_table.model().index(1, 4))
    link = [a for a in menu.actions() if a.menu() is not None][0].menu()
    [a for a in link.actions() if a.text() == 'Peak 1'][0].trigger()
    assert dlg.peaks[1]['width'] == dlg.peaks[0]['width']          # follows at once
    assert _shown(dlg.peaks_table, 1, 4).startswith('[=P1]')
    assert not dlg.peaks_table.item(1, 4).flags() & 2              # not editable (Qt.ItemIsEditable)
    dlg.perform_fit()
    f = dlg.fit_results
    assert f[2]['parameters']['center'] == 70.5
    assert f[1]['parameters']['sigma'] == pytest.approx(f[0]['parameters']['sigma'])
    assert _shown(dlg.peaks_table, 2, 2) == '[fixed] 70.5000'      # no ± for a fixed value
    assert '±' in _shown(dlg.peaks_table, 1, 4)
    dlg.copy_results_to_clipboard()
    lines = QApplication.clipboard().text().splitlines()
    assert lines[0].endswith('Fixed / linked')
    assert lines[2].endswith('Width =P1') and lines[3].endswith('Center fixed')
    # Fitted (free) again
    menu = dlg.peaks_constraint_menu(dlg.peaks_table.model().index(2, 2))
    [a for a in menu.actions() if a.text() == 'Fitted (free)'][0].trigger()
    assert 'center' not in dlg.peaks[2]['constraints']


def test_same_width_for_all_and_removing_a_peak_drops_its_links(dlg):
    menu = dlg.peaks_constraint_menu(dlg.peaks_table.model().index(0, 4))
    [a for a in menu.actions() if a.text().startswith('The same width for all')][0].trigger()
    assert all(dlg.peaks[k]['constraints']['width']['peak'] == dlg.peaks[0]['id']
               for k in (1, 2))
    menu = dlg.peaks_constraint_menu(dlg.peaks_table.model().index(2, 2))
    link = [a for a in menu.actions() if a.menu() is not None][0].menu()
    assert link.actions()[0].text().startswith('Peak 1 (now +')        # the distance now
    dlg.peaks_table.selectRow(0)
    dlg.remove_peak()                                                   # peak 1 removed
    assert all('width' not in (p.get('constraints') or {}) for p in dlg.peaks)


def test_links_are_kept_with_the_settings(dlg):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    dlg.set_constraint([1], 'height', {'kind': 'link', 'peak': dlg.peaks[0]['id']})
    settings = dlg.get_results()
    again = PeakFittingDialog(None, spectrum=dlg.spectrum, current_settings=settings)
    spec = again.peaks[1]['constraints']['height']
    assert spec['kind'] == 'link' and spec['value'] == pytest.approx(0.5)
    assert _shown(again.peaks_table, 1, 3).startswith('[P1×0.5]')
