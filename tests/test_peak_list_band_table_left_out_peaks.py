"""Peak list, Band table: two or more peaks of one spectrum in one band -
only the one nearest the band's position is shown, and the line under the
table counts the peaks left out (right also for three peaks)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _three_close_peaks():
    """Two spectra: the first with three peaks close together (1000, 1010,
    1020), the second with one peak at 1012."""
    x = np.linspace(900, 1100, 2001)

    def band(c):
        return np.exp(-0.5 * ((x - c) / 1.2) ** 2)
    return [{'x_scale': x, 'y_scale': band(1000) + band(1010) + band(1020), 'label': 'three',
             'metadata': {}},
            {'x_scale': x, 'y_scale': band(1012), 'label': 'one', 'metadata': {}}]


def test_three_peaks_in_one_band_show_the_nearest_and_count_the_others():
    from src.modules.data_analysis import peak_list as pl
    sp = _three_close_peaks()
    rows, index = pl.peak_table_with_index(sp, threshold=0.1, prominence=0.1, distance=0.001)
    assert len(rows) == 4
    columns, table, merged = pl.band_table(rows, index, sp, 'Position (x)', 15.0)
    assert len(columns) == 2 and merged == 2                         # one band, two left out
    centre = float(columns[1])
    shown = table[0][1]
    assert all(abs(shown - centre) <= abs(r[3] - centre) for r, i in zip(rows, index) if i == 0)
    columns, table, merged = pl.band_table(rows, index, sp, 'Position (x)', 5.0)
    assert len(columns) == 4 and merged == 0                         # split: own columns


def test_the_line_under_the_table_counts_the_peaks_left_out():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    dlg = PeakListDialog(None, _three_close_peaks(), threshold=0.1, prominence=0.1,
                         distance=0.001)
    dlg.show()
    dlg.tolerance.setValue(15.0)
    dlg.tabs.setCurrentIndex(2)
    app.processEvents()
    assert '2 peak(s) not shown' in dlg.band_info.text()
    dlg.tolerance.setValue(5.0)
    app.processEvents()
    assert 'not shown' not in dlg.band_info.text()
    dlg.close()
