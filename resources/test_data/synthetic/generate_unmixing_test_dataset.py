"""
generate_unmixing_test_dataset.py

A synthetic Raman map for trying endmember unmixing (2D Map -> Map Type
"Unmixing", VCA / N-FINDR):

unmixing_cell_map_demo.mat -- 50 x 40 pixels (WITec / Project FIVE .mat
format, 600-1800 cm-1 in 2 cm-1 steps) of one cell on glass, made of FOUR
substances with known spectra:

    1. glass (background)     -- broad hump around 1100 cm-1, sloping baseline
    2. protein (cytoplasm)    -- 1003, 1250, 1450, 1655 cm-1
    3. nucleus (DNA-rich)     -- 785, 1095, 1340, 1578 cm-1 (+ some protein)
    4. lipid (three droplets) -- 1065, 1300, 1440, 1660, 1745 cm-1

Every pixel is a mixture of the four (fractions summing to 1, smooth borders
between the regions); each substance also occurs (nearly) pure somewhere --
the glass around the cell, the middle of the cytoplasm, the middle of the
nucleus and of the droplets -- which is what endmember methods need. On top:
a smooth change of the overall intensity across the map (focus, +-10 %) and
pixel noise.

What to try: 2D Map, Map Type "Unmixing", Suggest number (-> 4), Update Map.
The four endmembers are the four substances (the markers sit in the glass,
the cytoplasm, the nucleus and a droplet); the abundance maps show the
regions. With 3 endmembers the fit-error map lights up where the missing
substance is (e.g. the droplets).

The true spectra and fraction maps: true_spectra() and true_fractions().
Run from this folder: python generate_unmixing_test_dataset.py
"""
import os

import numpy as np

N_COLS, N_ROWS = 50, 40
X = np.arange(600.0, 1801.0, 2.0)
NAMES = ('glass', 'protein', 'nucleus', 'lipid')
DROPLETS = ((31, 13), (35, 25), (14, 27))          # (column, row) centres


def _band(c, fwhm, h):
    return h * np.exp(-4 * np.log(2) * ((X - c) / fwhm) ** 2)


def true_spectra():
    """The four substances' spectra, shape (4, len(X)), in NAMES order."""
    glass = 0.30 + 0.0001 * (X - 600) + _band(1100, 160, 0.12)
    protein = (_band(1003, 8, 0.9) + _band(1250, 40, 0.35) + _band(1450, 28, 1.0)
               + _band(1655, 30, 0.9) + 0.30)
    nucleus = (_band(785, 12, 0.9) + _band(1095, 14, 0.7) + _band(1340, 24, 0.5)
               + _band(1578, 14, 0.45) + 0.3 * _band(1655, 30, 0.9) + 0.30)
    lipid = (_band(1065, 14, 0.45) + _band(1300, 18, 0.8) + _band(1440, 22, 1.4)
             + _band(1660, 16, 0.8) + _band(1745, 14, 0.5) + 0.30)
    return np.vstack([glass, protein, nucleus, lipid])


def _soft_inside(d, edge=1.2):
    """1 well inside (d < 0), 0 well outside, smooth over ~edge pixels."""
    return 1.0 / (1.0 + np.exp(d / (edge / 4.0)))


def true_fractions():
    """Fractions of the four substances per pixel, shape (rows*cols, 4)."""
    cc, rr = np.meshgrid(np.arange(N_COLS), np.arange(N_ROWS))
    cell = _soft_inside((np.hypot((cc - 25) / 18.0, (rr - 20) / 14.0) - 1) * 14.0)
    nuc = _soft_inside((np.hypot((cc - 21) / 6.0, (rr - 19) / 5.0) - 1) * 5.0)
    lip = np.zeros_like(cell)
    for c0, r0 in DROPLETS:
        lip = np.maximum(lip, _soft_inside(np.hypot(cc - c0, rr - r0) - 2.2, edge=0.9))
    f_nuc = cell * nuc
    f_lip = cell * (1 - nuc) * lip
    f_prot = cell * (1 - nuc) * (1 - lip)
    f_glass = 1 - cell
    F = np.stack([f_glass, f_prot, f_nuc, f_lip], axis=-1).reshape(-1, 4)
    return F / F.sum(axis=1, keepdims=True)


def make_data(seed=7, noise=0.012):
    rng = np.random.default_rng(seed)
    F = true_fractions()
    cols = np.tile(np.arange(N_COLS), N_ROWS)
    focus = 0.9 + 0.2 * cols / (N_COLS - 1)                  # intensity drift
    data = (F @ true_spectra()) * focus[:, None]
    return (data + rng.normal(0, noise, data.shape)).astype(np.float32)


def write(path):
    import scipy.io
    data = make_data()
    axisscale = np.empty((2, 2), dtype=object)
    axisscale[0, 0] = np.empty((0, 0))
    axisscale[0, 1] = np.array([''])
    axisscale[1, 0] = X.reshape(1, -1)
    axisscale[1, 1] = 'rel. 1/cm'
    imageaxisscale = np.empty((2, 2), dtype=object)
    imageaxisscale[0, 0] = (np.arange(N_COLS, dtype=float) * 0.5).reshape(1, -1)
    imageaxisscale[0, 1] = 'um'
    imageaxisscale[1, 0] = (np.arange(N_ROWS, dtype=float) * 0.5).reshape(1, -1)
    imageaxisscale[1, 1] = 'um'
    scipy.io.savemat(path, {'unmixing_map': {
        'name': 'synthetic cell map for unmixing', 'type': 'image',
        'imagesize': np.array([[N_COLS, N_ROWS]], dtype=np.uint8),
        'data': data, 'axisscale': axisscale, 'imageaxisscale': imageaxisscale,
        'history': 'generate_unmixing_test_dataset.py'}}, do_compression=True)


if __name__ == "__main__":
    out = os.path.dirname(os.path.abspath(__file__))
    write(os.path.join(out, "unmixing_cell_map_demo.mat"))
    print("Wrote: unmixing_cell_map_demo.mat")
