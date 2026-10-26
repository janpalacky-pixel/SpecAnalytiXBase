"""Draws the two explanatory figures used in the helps (run from the repo root):
resources/images/help_screenshots/calculations/area_over_a_range.png
resources/images/help_screenshots/calculations/voigt_area_tails.png"""
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.special import voigt_profile

OUT = os.path.join('resources', 'images', 'help_screenshots', 'calculations')
BLUE, RED = '#1f6fb4', '#c62828'
f = lambda t: 2 + 3 * np.exp(-((t - 5) / 2.2) ** 2)
x = np.arange(0, 11.0)


def style(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=8)
    ax.set_ylim(0, 6.2)
    ax.set_xlabel('x', fontsize=8)


fig, axs = plt.subplots(1, 3, figsize=(13.5, 4.3))
# 1 edges
ax = axs[0]; style(ax)
ax.plot(x, f(x), 'o-', color='k', ms=4, lw=1)
a, b = 2.5, 7.5
ax.axvspan(a, b, color='k', alpha=.05)
xs = np.r_[a, x[(x > a) & (x < b)], b]
ax.fill_between(xs, 0, np.interp(xs, x, f(x)), color=BLUE, alpha=.35, label='area counted (now)')
for lo, hi in ((a, 3), (7, b)):
    t = np.array([lo, hi])
    ax.fill_between(t, 0, np.interp(t, x, f(x)), color='none', hatch='///', edgecolor=RED)
ax.fill_between([], [], color='none', hatch='///', edgecolor=RED, label='missing before 1.5')
ax.text(5, 0.4, 'range 2.5 – 7.5', ha='center', fontsize=8)
ax.set_title('1  Range edges: before 1.5 the area ran only\nfrom the first to the last point inside (3 – 7)',
             fontsize=9.5, loc='left')
ax.legend(fontsize=7.5, loc='upper right', frameon=False)
# 2 gaps
ax = axs[1]; style(ax)
y = f(x)
ax.plot(x, y, 'o-', color='k', ms=4, lw=1)
for lo, hi in ((0, 2), (8, 10)):
    ax.axvspan(lo, hi, color='k', alpha=.05)
    m = (x >= lo) & (x <= hi)
    ax.fill_between(x[m], 0, y[m], color=BLUE, alpha=.35)
ax.plot([2, 8], [y[2], y[8]], '--', color=RED, lw=1.3)
ax.fill_between([2, 8], 0, [y[2], y[8]], color='none', hatch='///', edgecolor=RED)
ax.text(5, 1.0, 'counted by mistake before 1.5:\nthe gap between the ranges', ha='center',
        color=RED, fontsize=8.5)
ax.text(1, 5.6, 'range 1', ha='center', fontsize=8)
ax.text(9, 5.6, 'range 2', ha='center', fontsize=8)
ax.set_title('2  Two ranges (or an excluded part): now each\npart is integrated on its own',
             fontsize=9.5, loc='left')
# 3 coverage
ax = axs[2]; style(ax)
xs = np.arange(0, 7.0)
ax.plot(xs, f(xs), 'o-', color='k', ms=4, lw=1, label='a spectrum measured 0 – 6')
part = np.array([5.0, 6.0])
ax.fill_between(part, 0, f(part), color='none', hatch='///', edgecolor=RED,
                label='before 1.5: value from only this part\n(with no point inside, Normalization\nused the whole spectrum)')
ax.axvspan(5, 10, color=BLUE, alpha=.12)
ax.text(7.5, 5.6, 'range 5 – 10', ha='center', fontsize=8, color=BLUE)
ax.text(8.3, 3.0, 'now: no value (2D Map,\nBand Ratio, Group Statistics)\nor left unchanged\n(Normalization),\nand the spectrum is named',
        ha='center', va='top', fontsize=8)
ax.set_xlim(-0.3, 10.5)
ax.set_title('3  Range not completely inside a spectrum', fontsize=9.5, loc='left')
ax.legend(fontsize=7.5, loc='upper left', frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, 'area_over_a_range.png'), dpi=100)

fig, ax = plt.subplots(figsize=(7.5, 3.6))
ax.spines[['top', 'right']].set_visible(False)
ax.tick_params(labelsize=8)
t = np.linspace(-160, 160, 4000)
v = voigt_profile(t, 0.01, 1.0) / voigt_profile(0, 0.01, 1.0)
w = 100       # +-50 FWHM, FWHM = 2
ax.semilogy(t, v, color='k', lw=1.2)
ax.fill_between(t, 1e-6, v, where=abs(t) <= w, color=BLUE, alpha=.3,
                label='integrated before 1.5 (± 50 widths)')
ax.fill_between(t, 1e-6, v, where=abs(t) > w, color='none', hatch='///', edgecolor=RED,
                label='cut off before 1.5 (continues further):\nup to 0.6 % of the area')
ax.set_ylim(1e-5, 2)
ax.set_xlabel('distance from the peak centre (FWHM = 2)', fontsize=8)
ax.set_ylabel('height (log scale)', fontsize=8)
ax.set_title('Voigt peak: the slowly decaying sides reach very far; the area is now exact',
             fontsize=9.5, loc='left')
ax.legend(fontsize=7.5, loc='upper right', frameon=False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, 'voigt_area_tails.png'), dpi=100)
