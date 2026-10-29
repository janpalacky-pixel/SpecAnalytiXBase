"""Peak Fitting: the Amplitude Constraint is one for all spectra (default) or,
with 'Each spectrum its own' ticked, set for the spectra selected in the list
- e.g. Positive Peaks Only for the Raman spectra and Unrestricted for the CD
spectra - and each spectrum is fitted with its own."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis import peak_fitting_series as pfs
from src.modules.data_analysis.peak_fitting_manager import gaussian

app = QApplication.instance() or QApplication([])


def _spectra():
    """Two 'Raman' spectra (positive bands) and two 'CD' spectra (one band up,
    one down)."""
    x = np.linspace(0, 200, 801)
    rng = np.random.default_rng(4)
    out = []
    for i in range(2):
        y = gaussian(x, 1.0, 60, 4.0) + gaussian(x, 0.5, 140, 6.0)
        out.append({'label': f'raman : r{i + 1}', 'x_scale': x,
                    'y_scale': y + rng.normal(0, 0.003, x.size), 'metadata': {}})
    for i in range(2):
        y = gaussian(x, 0.8, 80, 8.0) - gaussian(x, 0.6, 130, 8.0)
        out.append({'label': f'cd : c{i + 1}', 'x_scale': x,
                    'y_scale': y + rng.normal(0, 0.003, x.size), 'metadata': {}})
    return out


def _window(sp, **kw):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    return PeakFittingDialog(None, spectrum=sp[0], series=sp, **kw)


def _select(dlg, rows):
    lst = dlg.spectra_list
    lst.clearSelection()
    for r in rows:
        lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)


def test_one_constraint_for_all_by_default():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _spectra()
    one = PeakFittingDialog(None, spectrum=sp[0])
    assert one.own_constraint_check.isHidden()
    dlg = _window(sp)
    assert not dlg.own_constraint_check.isChecked() and dlg.constraint_note.isHidden()
    dlg.amplitude_combo.setCurrentIndex(1)                        # Positive, for all
    assert all(dlg.constraint_of(k) == 'positive' for k in range(4))
    assert dlg.get_results()['amplitude_constraint'] == 'positive'


def test_each_spectrum_its_own_constraint():
    sp = _spectra()
    dlg = _window(sp)
    dlg.own_constraint_check.setChecked(True)
    assert not dlg.constraint_note.isHidden()
    _select(dlg, [0, 1])
    dlg.amplitude_combo.setCurrentIndex(1)                        # Raman: Positive
    _select(dlg, [2, 3])
    assert dlg.amplitude_combo.currentIndex() == 0                # CD: still the global one
    assert [dlg.constraint_of(k) for k in range(4)] == ['positive', 'positive',
                                                         'unrestricted', 'unrestricted']
    assert dlg.spectra_list.item(0).text().endswith('(+)')
    assert not dlg.spectra_list.item(2).text().endswith(')')
    _select(dlg, [1, 2])                                          # different: "mixed"
    assert dlg.amplitude_combo.currentText() == '— mixed —'
    assert '1 Positive Peaks Only' in dlg.constraint_note.text()
    dlg.list_all_button.click()
    dlg.auto_detect_peaks()
    res = dlg.fit_selected()
    assert all(r['ok'] for r in res)
    heights = [p['parameters']['height'] for p in res[2]['peaks']]
    assert min(heights) < -0.4                                    # the CD band down is kept
    raman = [p['parameters']['height'] for p in res[0]['peaks']]
    assert min(raman) >= 0
    dlg.own_constraint_check.setChecked(False)                    # back: one for all
    assert all(dlg.constraint_of(k) == dlg.global_constraint for k in range(4))
    assert not dlg.spectra_list.item(0).text().endswith('(+)')


def test_the_constraints_are_remembered():
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = _spectra()
    dlg = _window(sp)
    dlg.own_constraint_check.setChecked(True)
    _select(dlg, [2])
    dlg.amplitude_combo.setCurrentIndex(2)                        # c1: Negative
    settings = dlg.get_results()
    assert settings['constraint_per_spectrum'] and settings['own_constraints'][2] == 'negative'
    again = PeakFittingDialog(None, spectrum=sp[0], current_settings=settings, series=sp)
    assert again.own_constraint_check.isChecked() and again.constraint_of(2) == 'negative'
    assert again.constraint_of(0) == 'unrestricted'


def test_independent_fits_with_their_own_constraints():
    sp = _spectra()
    start = [{'model': 'Gaussian', 'center': 80.0, 'amplitude': 0.8, 'width': 8.0},
             {'model': 'Gaussian', 'center': 130.0, 'amplitude': 0.5, 'width': 8.0}]
    res = pfs.fit_series_independent([sp[2], sp[3]], start, starts=[start, start],
                                     constraints=['positive', 'unrestricted'],
                                     parallel={'processing_mode': 'serial'})
    h_pos = [p['parameters']['height'] for p in res[0]['peaks']]
    h_free = [p['parameters']['height'] for p in res[1]['peaks']]
    assert min(h_pos) >= 0 and min(h_free) < -0.4
