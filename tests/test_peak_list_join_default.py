"""Peak list, tab Plot: "Join the same" starts with "band (peak by its
position)" - ticking Join gives lines that stay on their bands; "peak number"
can still be chosen."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def test_join_starts_with_band():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    x = np.linspace(0, 100, 501)
    spectra = [{'label': f'scan : {i + 1:02d}', 'x_scale': x, 'metadata': {},
                'y_scale': np.exp(-((x - 50) / 2) ** 2) + np.exp(-((x - 70) / 2) ** 2)
                + (np.exp(-((x - 30) / 2) ** 2) if i < 3 else 0)} for i in range(6)]
    dlg = PeakListDialog(None, spectra)
    dlg.tabs.setCurrentIndex(1)
    dlg.y_combo.setCurrentText('Position (x)')
    assert dlg.join_by.currentData() == 'band'
    dlg.join_check.setChecked(True)
    lines = dlg.figure.axes[0].lines
    assert len(lines) == 3 and all(np.ptp(line.get_ydata()) < 1 for line in lines)
    assert dlg.tolerance.isVisibleTo(dlg)
    assert [dlg.join_by.itemData(i) for i in range(dlg.join_by.count())] == ['number', 'band']
