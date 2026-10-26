"""Draws the explanatory figures of the Peak Detection help with the
program's own peak detection (run from the repo root):
resources/images/help_screenshots/peak_detection/
  labels_threshold_before_now.png   raman_2comp_clean, 11 spectra
  noisy_cd_signal_to_noise.png      cd_2comp_noisy, Peaks: Both
  cd_moving_minimum.png             why a CD minimum moves (not a band)"""
import os
import sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)                     # the repository: paths below are relative to it
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from src.modules.data_analysis import peak_list as pl
from src.modules.data_analysis.peak_detection_manager import PeakDetector

OUT = os.path.join('resources', 'images', 'help_screenshots', 'peak_detection')
SYN = os.path.join('resources', 'test_data', 'synthetic')
os.makedirs(OUT, exist_ok=True)


def sheet(name, which='Spectra'):
    return pd.read_excel(os.path.join(SYN, name + '.xlsx'), sheet_name=which)


def panel(ax, x, ys, title, colours=None, **detect):
    """Plot the spectra and mark their peaks exactly as Detect Peaks does."""
    tmp = Figure()
    canvas = FigureCanvasAgg(tmp)
    a = tmp.add_subplot(111)
    for i, y in enumerate(ys):
        a.plot(x, y)
        ax.plot(x, y, lw=1, color=None if colours is None else colours[i])
    det = PeakDetector()
    det.detect_peaks(canvas, detect.get('threshold', 0.0), 8, 0, detect.get('decimals', 1),
                     'fixed', 'x_only', True, 0.1, 0.05, detect.get('mode', 'Positive'),
                     labels=detect.get('labels', 'band'), snr=detect.get('snr', 8.0))
    for dot in det.peak_lines:
        ax.plot(dot.get_xdata(), dot.get_ydata(), 'o', color='#d32f2f', ms=4.5)
    for t in det.peak_texts:
        ax.text(*t.get_position(), t.get_text(), fontsize=8, ha='center', va=t.get_va())
    ax.set_title(title, fontsize=9.5)
    ax.tick_params(labelsize=8)
    ax.spines[['top', 'right']].set_visible(False)
    return len(det.peak_lines), len(det.peak_texts)


def figure_labels():
    d = sheet('raman_2comp_clean')
    x = d.iloc[:, 0].values
    cols = ['raman_01', 'raman_05', 'raman_06', 'raman_07', 'raman_08', 'raman_09',
            'raman_15', 'raman_16', 'raman_17', 'raman_18', 'raman_19']
    import matplotlib.cm as cm
    colours = [cm.plasma(i / len(cols)) for i in range(len(cols))]
    ys = [d[c].values for c in cols]
    fig = Figure(figsize=(12, 7.2))
    FigureCanvasAgg(fig)
    a1, a2 = fig.subplots(2, 1, sharex=True)
    n1 = panel(a1, x, ys, 'Before: Threshold 0.5, a number on every peak - the band at 344 is '
               'missed, the numbers pile up', colours, threshold=0.5, labels='all', snr=0, decimals=2)
    n2 = panel(a2, x, ys, 'Now: Threshold 0 and signal-to-noise 8 (judged locally), Labels once per '
               'band - every band, each number once', colours, decimals=2)
    a2.set_xlabel('Raman shift', fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'labels_threshold_before_now.png'), dpi=90)
    print('labels', n1, n2)


def figure_noise():
    d = sheet('cd_2comp_noisy')
    x = d.iloc[:, 0].values
    ys = [d[c].values for c in d.columns[1:]]
    fig = Figure(figsize=(12, 7.2))
    FigureCanvasAgg(fig)
    a1, a2 = fig.subplots(2, 1, sharex=True)
    n1 = panel(a1, x, ys, 'Signal-to-noise 0 (no noise limit): the noise of the weak spectra is '
               'taken for peaks', mode='Both', snr=0)
    n2 = panel(a2, x, ys, 'Signal-to-noise 8 (default): the three real bands; a band that moves '
               'is written as its range', mode='Both')
    a2.set_xlabel('Wavelength (nm)', fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'noisy_cd_signal_to_noise.png'), dpi=90)
    print('noise', n1, n2)


def figure_moving_minimum():
    d = sheet('cd_2comp_clean')
    pure = sheet('cd_2comp_clean', 'Pure_components')
    truth = sheet('cd_2comp_clean', 'Ground_truth')
    x = d.iloc[:, 0].values
    fig = Figure(figsize=(12, 4.4))
    FigureCanvasAgg(fig)
    a1, a2 = fig.subplots(1, 2, gridspec_kw={'width_ratios': [1.25, 1]})
    for i, (c, colour) in enumerate((('cd_01', '#1565C0'), ('cd_30', '#C62828'))):
        y = d[c].values
        a1.plot(x, y, color=colour, lw=1.6, label=f'{c} (mixture)')
        p = [q for q in pl.spectrum_peaks(x, y, mode='Negative') if q['x'] > 240]
        if p:
            a1.plot([p[0]['x']], [p[0]['y']], 'o', color=colour, ms=6)
            a1.annotate(f"minimum {p[0]['x']:.1f}", (p[0]['x'], p[0]['y']),
                        textcoords='offset points', xytext=(8, -12), fontsize=8, color=colour)
    neg = truth[(truth['Sign'] == 'negative') & (truth['Peak_center'] > 235)]
    for _, r in neg.iterrows():
        a1.axvline(r['Peak_center'], color='grey', ls=':', lw=1)
        a1.text(r['Peak_center'], 0.13, f"band {r['Peak_center']:g}\n({r['Component'][-1]})",
                fontsize=7.5, ha='center', color='grey')
    k = 0.3      # the pure spectra are per unit amount: scaled to the mixtures
    a1.plot(pure.iloc[:, 0], k * pure.iloc[:, 1], color='grey', lw=0.9, ls='--',
            label='component 1 (\u00d70.3)')
    a1.plot(pure.iloc[:, 0], k * pure.iloc[:, 2], color='grey', lw=0.9, ls='-.',
            label='component 2 (\u00d70.3)')
    a1.set_xlim(225, 270)
    lo = min(float(np.min(d['cd_01'])), float(np.min(d['cd_30'])), float(k * pure.iloc[:, 1:].values.min()))
    a1.set_ylim(lo * 1.15, 0.25)
    a1.legend(fontsize=7.5, loc='lower left')
    a1.set_title('The minimum is the sum of three overlapping negative bands', fontsize=9.5)
    a1.set_xlabel('Wavelength (nm)', fontsize=8)
    pos = []
    for c in d.columns[1:]:
        p = [q for q in pl.spectrum_peaks(x, d[c].values, mode='Negative') if q['x'] > 240]
        pos.append(p[0]['x'] if p else np.nan)
    a2.plot(range(1, len(pos) + 1), pos, 'o-', color='#d32f2f', ms=4)
    for _, r in neg.iterrows():
        a2.axhline(r['Peak_center'], color='grey', ls=':', lw=1)
        a2.text(len(pos) + 0.6, r['Peak_center'], f"{r['Peak_center']:g}", fontsize=7.5,
                va='center', color='grey')
    a2.set_xlabel('Spectrum (cd_01 ... cd_30)', fontsize=8)
    a2.set_ylabel('Position of the minimum (nm)', fontsize=8)
    a2.set_title('Its position moves 247 \u2192 256 nm as the mixture changes', fontsize=9.5)
    for a in (a1, a2):
        a.tick_params(labelsize=8)
        a.spines[['top', 'right']].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'cd_moving_minimum.png'), dpi=90)
    print('moving', min(pos), max(pos))


figure_labels()
figure_noise()
figure_moving_minimum()
