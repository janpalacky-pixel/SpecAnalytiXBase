"""Screenshots for the 2D Map help, section Unmixing (run offscreen):
python tools/help_pictures/make_unmixing_figures.py"""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
import numpy as np
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

app = QApplication.instance() or QApplication([])
from src.views import button_icons as _bi   # icons on the dialog buttons, as in the program
_bi.install(app)
for n in ('information', 'warning', 'critical'):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
from src.modules.core.spectrum_manager import SpectrumManager
from src.controllers.visualization_analysis.map2d_controller import Map2DController
from src.views.dialogs.visualization_analysis.map2d_dialog import Map2DDialog

OUT = os.path.join('resources', 'images', 'help_screenshots', 'map2d')
m = SpectrumManager()
m.load_spectrum_from_file(os.path.join('resources', 'test_data', 'synthetic',
                                       'unmixing_cell_map_demo.mat'))
spectra = [{'label': l, 'x_scale': s.x_scale, 'y_scale': s.y_scale, 'metadata': s.metadata}
           for l, s in m.spectra.items()]


class _Main:
    view = None


def _crop_white(img, margin=6):
    """Cut the white space around the picture (the map canvas keeps empty
    space above and below an equal-aspect map)."""
    from PyQt5.QtGui import QColor
    w, h = img.width(), img.height()
    def white(x, y):
        c = QColor(img.pixel(x, y))
        return c.red() > 245 and c.green() > 245 and c.blue() > 245
    rows = [y for y in range(h) if any(not white(x, y) for x in range(0, w, 2))]
    cols = [x for x in range(w) if any(not white(x, y) for y in range(0, h, 2))]
    if not rows or not cols:
        return img
    x0, x1 = max(0, cols[0] - margin), min(w, cols[-1] + margin)
    y0, y1 = max(0, rows[0] - margin), min(h, rows[-1] + margin)
    return img.copy(x0, y0, x1 - x0, y1 - y0)


def save(widget, name, width=1000, crop=False):
    app.processEvents()
    img = widget.grab().toImage()
    if crop:
        img = _crop_white(img)
    if img.width() > width:
        img = img.scaledToWidth(width, Qt.SmoothTransformation)
    img.save(os.path.join(OUT, name))
    print('wrote', name)


d = Map2DDialog(None, Map2DController(_Main()), spectra)
d.resize(1300, 860)
d.show()
app.processEvents()
d._equal_aspect_cb.setChecked(True)
d._radio_em.setChecked(True)
d._on_mode_changed(d._radio_em)
# Suggest number opens a window: click "Use ... (clearly above the noise)" automatically
from src.views.dialogs.visualization_analysis import map2d_dialog as _md
_md._SuggestEndmembersDialog.exec_ = lambda self: self.clear_btn.click() or 1
d._suggest_n_endmembers()
d._compute_map()
res = d.controller.get_em_result()
corr = np.corrcoef(np.vstack([res.H, np.vstack([s['y_scale'] for s in spectra])[[0]]]))
# browse the lipid endmember (the one with the 1745 band) and click its pixel
lipid = int(np.argmax(res.H[:, np.argmin(np.abs(res.x_axis - 1745))]))
d._component_combo.setCurrentIndex(lipid)
app.processEvents()
pix = int(res.endmember_indices[lipid])
r, c = divmod(pix, d._cols_spin.value())


class _Click:
    inaxes = d._map_canvas.ax
    xdata, ydata, button, dblclick = float(c), float(r), 1, False


d._on_map_click(_Click())
app.processEvents()
save(d, 'unmixing_abundance.png', 1000)
d._decomp_n_spin.setValue(3)
d._compute_map()
d._em_error_map_cb.setChecked(True)
app.processEvents()
save(d._map_canvas, 'unmixing_fit_error.png', 600, crop=True)
d.close()

# the four true spectra the demo map was made of (generate_unmixing_test_dataset.py)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.join('resources', 'test_data', 'synthetic'))
import generate_unmixing_test_dataset as truth
S = truth.true_spectra()
colors = ('#7f7f7f', '#1f77b4', '#d62728', '#2ca02c')
labels = ('glass (background)', 'protein (cytoplasm)', 'nucleus (DNA-rich)', 'lipid (droplets)')
fig, ax = plt.subplots(figsize=(7.4, 3.6), dpi=100)
for k in range(4):
    off = 1.6 * (3 - k)
    ax.plot(truth.X, S[k] + off, color=colors[k], lw=1.4)
    ax.text(1805, S[k][-1] + off, labels[k], color=colors[k], va='center', fontsize=9)
marks = {'glass (background)': [1100], 'protein (cytoplasm)': [1003, 1250, 1450, 1655],
         'nucleus (DNA-rich)': [785, 1095, 1340, 1578], 'lipid (droplets)': [1065, 1300, 1440, 1660, 1745]}
for k, lab in enumerate(labels):
    off = 1.6 * (3 - k)
    for b in marks[lab]:
        y = S[k][np.argmin(np.abs(truth.X - b))] + off
        ax.annotate(str(b), (b, y), xytext=(0, 3), textcoords='offset points',
                    ha='center', fontsize=7, color=colors[k])
ax.set_xlim(600, 2050)
ax.set_xticks(range(600, 1801, 200))
ax.set_yticks([])
ax.set_xlabel('Raman shift / cm$^{-1}$')
ax.set_title('Demo map: the four pure spectra it is made of (offset for clarity)', fontsize=10)
for side in ('top', 'right', 'left'):
    ax.spines[side].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, 'unmixing_demo_spectra.png'))
print('wrote unmixing_demo_spectra.png')
