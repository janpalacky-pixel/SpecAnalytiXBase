"""Help figure: how Suggest number finds 'above the noise' and 'clearly above the noise'
(Glenodinium map). Needs the Glenodinium snapshot (see glenodinium_data.py;
skipped without it):
python tools/help_pictures/make_suggest_explained_figure.py"""
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.modules.visualization_analysis import endmember_unmixing as eu

sys.path.insert(0, os.path.join(ROOT, 'tools', 'help_pictures'))
import glenodinium_data
_data = glenodinium_data.load()
if _data is None:
    print('Glenodinium snapshot not found: the Suggest figure is skipped.')
    sys.exit(0)
Y = _data['Y'].astype(float)
N, L = Y.shape
s, _ = eu.svd_basis(Y)
n, plateau = eu.noise_plateau(s)
m = len(s)
k0, k1 = max(4, int(0.05 * m)), max(max(4, int(0.05 * m)) + 4, int(0.5 * m))
d2 = np.diff(Y, n=2, axis=1).ravel()
sigma_old = 1.4826 * np.median(np.abs(d2 - np.median(d2))) / np.sqrt(6)
old_limit = 1.2 * sigma_old * (np.sqrt(N) + np.sqrt(L))
print('n', n, 'old sigma', sigma_old, 'old limit', old_limit,
      'plateau at n', plateau[n], 'limit', 1.15 * plateau[n])

fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.6), dpi=100)
k = np.arange(1, m + 1)
a.loglog(k, s, '.-', ms=3, lw=0.8, color='#1565C0', label='singular values (all 1600)')
a.axvspan(k0 + 1, k1, color='#BDBDBD', alpha=0.35,
          label=f'flat part used for the fit (components {k0 + 1}–{k1})')
a.loglog(k, plateau, '--', color='#424242', lw=1.2, label='noise plateau (fitted line)')
a.loglog(k, 1.15 * plateau, ':', color='#B71C1C', lw=1.5,
         label=f'noise limit = 1.15 × plateau (≈ {1.15 * plateau[n]:.0f})')
a.axhline(old_limit, color='#6A1B9A', ls='-.', lw=1.2,
          label=f'limit from a typical pixel\'s noise ≈ {old_limit:.0f} ({int(np.sum(s > old_limit))} values above it)')
a.plot([n], [s[n - 1]], 's', ms=9, mfc='none', mec='#B71C1C', mew=2,
       label=f'last above the noise: {n}')
a.set_xlabel('Component (log scale)')
a.set_ylabel('Singular value (log scale)')
a.set_title('1) "Above the noise": compare with the fitted noise line', fontsize=10)
a.legend(fontsize=7.5, loc='upper right')
a.grid(alpha=0.3, which='both')

shown = 20
ratio = s[:shown] / plateau[:shown]
kk = np.arange(1, shown + 1)
colors = ['#E65100' if r > 2.0 else ('#C62828' if r > 1.15 else '#90A4AE') for r in ratio]
b.bar(kk, ratio, color=colors, alpha=0.85)
b.axhline(1.0, color='#424242', ls='--', lw=1, label='noise line (plateau)')
b.axhline(1.15, color='#B71C1C', ls=':', lw=1.5, label='1.15 \u00d7: above the noise')
b.axhline(2.0, color='#E65100', ls='-.', lw=1.5, label='2 \u00d7: clearly above the noise')
b.set_yscale('log')
b.set_yticks([1, 1.15, 2, 5, 10, 20, 50, 100])
b.set_yticklabels(['1', '1.15', '2', '5', '10', '20', '50', '100'])
for k_, r_ in zip(kk, ratio):
    if r_ < 6:
        b.text(k_, r_ * 1.04, f'{r_:.1f}', ha='center', va='bottom', fontsize=6.5)
clear = eu.clear_count(s, plateau, n)
b.set_xticks(kk)
b.tick_params(axis='x', labelsize=7)
b.set_xlabel('Component')
b.set_ylabel('Singular value / noise line (log scale)')
b.set_title(f'2) Each value \u00f7 noise line: {clear} clearly above, {n} above the noise',
            fontsize=10)
b.legend(fontsize=7.5, loc='upper right')
b.grid(alpha=0.3, axis='y')
fig.suptitle('How Suggest number reads the singular values — Glenodinium map, '
             '21 000 spectra × 1 600 points', fontsize=11)
fig.tight_layout()
out = os.path.join('resources', 'images', 'help_screenshots', 'map2d', 'unmixing_suggest_explained.png')
fig.savefig(out)
print('wrote', out)
