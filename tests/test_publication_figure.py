"""Save plot for publication: a copy in a journal's column width, one text
size, lines at least so thick, at the chosen dpi - the plot on the screen
unchanged; the window remembers the choices."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _figure():
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    fig = Figure(figsize=(10, 6))
    FigureCanvasQTAgg(fig)
    ax = fig.add_subplot()
    ax.plot([1, 2, 3], [1, 4, 9], lw=0.5, label='sp001')
    ax.set_xlabel('Wavenumber')
    ax.set_title('Spectra')
    ax.legend()
    return fig


@pytest.mark.parametrize('ext', ['tif', 'png', 'pdf', 'svg', 'eps'])
def test_saved_in_each_kind(tmp_path, ext):
    from src.modules.visualization import publication_figure as pf
    fig = _figure()
    path = str(tmp_path / f'fig.{ext}')
    copy = pf.save_for_publication(fig, path, 8.5, 6.5, 600, 8, 1.0)
    assert os.path.getsize(path) > 1000
    assert tuple(fig.get_size_inches()) == (10, 6) and fig.axes[0].lines[0].get_linewidth() == 0.5
    assert copy.get_size_inches()[0] == pytest.approx(8.5 / 2.54)
    assert copy.axes[0].lines[0].get_linewidth() == 1.0
    assert copy.axes[0].xaxis.label.get_fontsize() == 8 and copy.axes[0].title.get_fontsize() == 9
    if ext == 'tif':
        from PIL import Image
        im = Image.open(path)
        assert im.size == pytest.approx(pf.pixels(8.5, 6.5, 600), abs=2)
        assert round(im.info['dpi'][0]) == 600


def test_the_window(tmp_path):
    from src.views.dialogs.visualization.publication_dialog import PREF_KEY, PublicationDialog

    class Prefs(dict):
        def set(self, k, v):
            self[k] = v
    prefs = Prefs()
    dlg = PublicationDialog(_figure(), preferences=prefs)
    dlg.column_combo.setCurrentIndex(2)                         # 2 columns
    assert dlg.width_spin.value() == 17.5
    dlg.width_spin.setValue(10.0)
    assert dlg.column_combo.currentData() is None               # own width
    dlg.dpi_combo.setCurrentIndex(dlg.dpi_combo.findData(300))
    assert '1181' in dlg.pixels_label.text()                    # 10 cm at 300 dpi
    path = dlg.save(str(tmp_path / 'f.png'))
    assert path and os.path.exists(path) and prefs[PREF_KEY]['dpi'] == 300
    again = PublicationDialog(_figure(), preferences=prefs)
    assert again.width_spin.value() == 10.0 and again.dpi_combo.currentData() == 300
