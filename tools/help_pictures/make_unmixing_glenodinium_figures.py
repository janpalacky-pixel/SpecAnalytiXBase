"""Help screenshots of Unmixing on the real Glenodinium map (21 000 spectra).
Needs the Glenodinium snapshot (see glenodinium_data.py; skipped without it):
python tools/help_pictures/make_unmixing_glenodinium_figures.py"""
import json
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])
from src.views import button_icons as _bi   # icons on the dialog buttons, as in the program
_bi.install(app)
for n in ('information', 'warning', 'critical'):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
from src.controllers.visualization_analysis.map2d_controller import Map2DController
from src.views.dialogs.visualization_analysis import map2d_dialog as md

OUT = os.path.join('resources', 'images', 'help_screenshots', 'map2d')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'help_pictures'))
import glenodinium_data
data = glenodinium_data.load()
if data is None:
    print('Glenodinium snapshot not found: the Unmixing pictures of the real map are skipped.')
    sys.exit(0)
meta = data['meta']
x = data['x']
Yall = data['Y']
labels, uids = data['labels'], data['uids']
spectra = []
for i, (lab, uid) in enumerate(zip(labels, uids)):
    m = dict(meta)
    m['unique_id'] = str(uid)
    spectra.append({'label': str(lab), 'x_scale': x, 'y_scale': Yall[i].astype(float),
                    'metadata': m})
del data, Yall
print('spectra ready', flush=True)


def save(widget, name, width=1000):
    app.processEvents()
    img = widget.grab().toImage()
    if img.width() > width:
        img = img.scaledToWidth(width, Qt.SmoothTransformation)
    img.save(os.path.join(OUT, name))
    print('wrote', name, flush=True)


class _Main:
    view = None


d = md.Map2DDialog(None, Map2DController(_Main()), spectra)
d.resize(1700, 960)
d.show()
app.processEvents()
d._equal_aspect_cb.setChecked(True)
d._radio_em.setChecked(True)
d._on_mode_changed(d._radio_em)
print('dims', d._rows_spin.value(), d._cols_spin.value(), flush=True)

# the Suggest window
est = d.controller.estimate_n_endmembers(spectra)
print('suggest', est['n'], est['clear'], flush=True)
sd = md._SuggestEndmembersDialog(est, d)
sd.resize(700, 520)
sd.show()
save(sd, 'unmixing_glen_suggest.png', 700)
sd.close()

d._decomp_n_spin.setValue(6)
d._compute_map()
res = d.controller.get_em_result()
print('pixels', [(int(i) // 150 + 1, int(i) % 150 + 1) for i in res.endmember_indices],
      'k', res.denoise_k, 'lof', round(res.lof, 2), flush=True)
# browse the endmember with sharp bands around 1520 cm-1 (carotenoid-like)
sharp = 0                         # E1: the ring of bodies along the cell edge
d._component_combo.setCurrentIndex(sharp)
app.processEvents()
r, c = divmod(int(res.endmember_indices[sharp]), d._cols_spin.value())


class _Click:
    inaxes = d._map_canvas.ax
    xdata, ydata, button, dblclick = float(c), float(r), 1, False


d._on_map_click(_Click())
save(d, 'unmixing_glen_dialog.png', 1100)

ad = md._EndmemberSpectraDialog(res, d._rows_spin.value(), d._cols_spin.value(), 'viridis', d)
ad.grid_radio.setChecked(True)
ad.resize(1100, 760)
ad.show()
save(ad, 'unmixing_glen_all.png', 1000)
ad.stacked_radio.setChecked(True)
ad.norm_cb.setChecked(True)
save(ad, 'unmixing_glen_stacked.png', 900)
ad.close()

# without denoising, for comparison
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
H_clean = res.H.copy()
idx_clean = res.endmember_indices.copy()
d._em_denoise_cb.setChecked(False)
d._compute_map()
raw = d.controller.get_em_result()
fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)
for ax, H, idx, title in ((axes[0], raw.H, raw.endmember_indices, 'without denoising'),
                          (axes[1], H_clean, idx_clean, 'Denoise first (auto: 13 SVD components)')):
    Hn = H / np.abs(H).max(axis=1, keepdims=True)
    for k in range(len(Hn)):
        rr, cc = divmod(int(idx[k]), 150)
        ax.plot(res.x_axis, Hn[k] + 1.2 * (len(Hn) - 1 - k), lw=0.6)
        ax.text(res.x_axis[-1], 1.2 * (len(Hn) - 1 - k) + 0.3, f' E{k + 1}\n r{rr + 1} c{cc + 1}',
                fontsize=7, va='center')
    ax.set_title(title, fontsize=10)
    ax.set_xlabel('Raman shift / cm$^{-1}$')
    ax.set_yticks([])
    ax.set_xlim(res.x_axis[0], res.x_axis[-1] + 450)
fig.suptitle('Glenodinium map, 6 endmembers (VCA), each scaled to max = 1', fontsize=11)
fig.tight_layout()
fig.savefig(os.path.join(OUT, 'unmixing_glen_denoise.png'), dpi=90)
print('wrote unmixing_glen_denoise.png', 'raw pixels',
      [(int(i) // 150 + 1, int(i) % 150 + 1) for i in raw.endmember_indices], flush=True)
