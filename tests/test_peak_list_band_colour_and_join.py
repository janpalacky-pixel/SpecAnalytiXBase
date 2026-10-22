"""Peak list, tab Plot: Colour = Band and Join the same band. The peaks of
all spectra at the same position (within ±) are one band: one colour, one
line - so when a band is missing in some spectra the lines do not jump to
the next band (as the peak number does)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _series():
    """Six spectra with bands at 30, 50 and 70; the band at 30 is missing in
    the last three (as if it disappeared on heating)."""
    x = np.linspace(0, 100, 501)
    out = []
    for i in range(6):
        y = np.exp(-((x - 50) / 2) ** 2) + np.exp(-((x - 70) / 2) ** 2)
        if i < 3:
            y = y + np.exp(-((x - 30) / 2) ** 2)
        out.append({'label': f'scan : {i + 1:02d}', 'x_scale': x, 'y_scale': y, 'metadata': {}})
    return out


def _plot():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    dlg = PeakListDialog(None, _series())
    dlg.tabs.setCurrentIndex(1)
    dlg.x_combo.setCurrentText('Spectrum (order in the list)')
    dlg.y_combo.setCurrentText('Position (x)')
    return dlg


def test_join_by_peak_number_jumps_join_by_band_does_not():
    dlg = _plot()
    dlg.join_check.setChecked(True)
    assert not dlg.tolerance.isVisibleTo(dlg)
    first = dlg.figure.axes[0].lines[0].get_ydata()          # "Peak 1"
    assert np.ptp(first) > 10                                # 30 in some spectra, 50 in others
    dlg.join_by.setCurrentIndex(dlg.join_by.findData('band'))
    assert dlg.tolerance.isVisibleTo(dlg)
    lines = dlg.figure.axes[0].lines
    assert len(lines) == 3
    assert all(np.ptp(line.get_ydata()) < 1 for line in lines)   # each stays on its band
    assert sorted(len(line.get_ydata()) for line in lines) == [3, 6, 6]
    texts = [t.get_text() for t in dlg.figure.axes[0].get_legend().get_texts()]
    assert 'Band 30 (line)' in texts or 'Band 30.0 (line)' in texts


def test_colour_by_band():
    dlg = _plot()
    dlg.colour_combo.setCurrentText('Band (peak by its position)')
    assert dlg.tolerance.isVisibleTo(dlg)
    ax = dlg.figure.axes[0]
    assert len(ax.collections) == 3                          # one colour per band
    for c in ax.collections:
        assert np.ptp(c.get_offsets()[:, 1]) < 1
    dlg.join_check.setChecked(True)
    dlg.join_by.setCurrentIndex(dlg.join_by.findData('band'))
    ax = dlg.figure.axes[0]
    texts = [t.get_text() for t in ax.get_legend().get_texts()]
    assert not any('(line)' in t for t in texts)             # the points already name them
    dlg.x_combo.setCurrentText('Peak by its position, on the x scale')
    assert not dlg.join_check.isEnabled() and not dlg.join_by.isEnabled()
