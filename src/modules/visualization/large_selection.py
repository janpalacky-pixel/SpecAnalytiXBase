# src/modules/visualization/large_selection.py
"""Plotting very many spectra: which of the selected spectra are drawn.

Drawing is the slow part of plotting many spectra, and almost all of it is
matplotlib's single canvas.draw() at the end, which can neither report
progress nor be interrupted (measured with 1 600-point spectra: 1 000
spectra 0.3 s to create the lines + 5 s to draw them; 5 000: 1.4 s + 24 s;
drawing them as one LineCollection or without antialiasing did not help).

So when more spectra are selected than a threshold, the plot types that
draw one line per spectrum show a *preview*: an evenly spread subset. The
selection itself is never changed -- every analysis still uses all
selected spectra; only the picture is affected. "Plot all" draws every
spectrum (the Overlay plot then in portions, with progress and Stop; see
src/controllers/visualization/large_plot_controller.py).

Qt-free.
"""

import numpy as np

DEFAULT_SETTINGS = {
    'threshold': 2000,       # more selected spectra than this -> preview
    'preview_count': 1000,   # how many spectra the preview draws
    'mode': 'preview',       # 'preview' or 'all'
}

# Tool windows (FFT Denoising, X-axis alignment, Isosbestic points,
# 2D Correlation, ...) redraw after every change, so they draw at most this
# many spectra (an evenly spread subset; the calculation always uses all of
# them). Stored as its own preference (see large_plot_controller).
DEFAULT_DIALOG_COUNT = 100


def normalized_dialog_count(value):
    try:
        return int(min(max(int(value), 10), 10_000_000))
    except (TypeError, ValueError):
        return DEFAULT_DIALOG_COUNT

# Plot types that draw one line (or panel) per selected spectrum. Not
# limited: Heatmap (one image), Mean ± SD and Difference (their mean must be
# the mean of ALL selected spectra, not of a preview) and Single spectrum.
LIMITED_PLOT_TYPES = ('Overlay plot', 'Grid plot', 'Waterfall plot')

MODES = ('preview', 'all')


def normalized_settings(settings=None):
    s = dict(DEFAULT_SETTINGS)
    s.update({k: v for k, v in (settings or {}).items() if k in DEFAULT_SETTINGS})
    try:
        s['threshold'] = int(min(max(int(s['threshold']), 10), 10_000_000))
    except (TypeError, ValueError):
        s['threshold'] = DEFAULT_SETTINGS['threshold']
    try:
        s['preview_count'] = int(min(max(int(s['preview_count']), 10), s['threshold']))
    except (TypeError, ValueError):
        s['preview_count'] = min(DEFAULT_SETTINGS['preview_count'], s['threshold'])
    if s['mode'] not in MODES:
        s['mode'] = DEFAULT_SETTINGS['mode']
    return s


def dialog_subset(items, limit, keep=None):
    """For drawing in a tool window: (items to draw, number of items). At
    most `limit` items, evenly spread (first and last included); items for
    which keep(item) is true (e.g. the reference spectrum) are always kept.
    Only the picture is affected -- callers compute with all items."""
    items = list(items)
    n = len(items)
    if limit is None or n <= limit:
        return items, n
    idx = set(preview_indices(n, max(int(limit), 1)))
    if keep is not None:
        idx.update(i for i, it in enumerate(items) if keep(it))
    return [items[i] for i in sorted(idx)], n


def shown_note(n_shown, n_total):
    """'' or e.g. '300 of 3 000 shown' (for a plot title)."""
    if n_shown >= n_total:
        return ''
    fmt = lambda v: f'{v:,}'.replace(',', '\u202f')
    return f'{fmt(n_shown)} of {fmt(n_total)} shown'


def preview_indices(n, count):
    """`count` indices spread evenly over range(n), first and last included
    (all of them if n <= count)."""
    if n <= count:
        return list(range(n))
    if count <= 1:
        return [0]
    return sorted({int(round(v)) for v in np.linspace(0, n - 1, count)})


def needs_preview(n_selected, plot_type, settings=None, plot_all=False):
    """True if the plot should show a preview instead of all spectra."""
    s = normalized_settings(settings)
    return (not plot_all and s['mode'] == 'preview'
            and plot_type in LIMITED_PLOT_TYPES and n_selected > s['threshold'])


def is_large(n_selected, plot_type, settings=None):
    """True if drawing all selected spectra counts as large (more than the
    threshold, in a plot type that draws one line per spectrum)."""
    s = normalized_settings(settings)
    return plot_type in LIMITED_PLOT_TYPES and n_selected > s['threshold']


def annotate_shown(ax, n_shown, n_total):
    """Small grey note in the top right corner of `ax` when only a subset
    of the spectra is drawn (e.g. '300 of 3 000 shown (evenly spread)')."""
    note = shown_note(n_shown, n_total)
    if note:
        ax.text(0.99, 0.99, note + ' (evenly spread)', transform=ax.transAxes,
                ha='right', va='top', fontsize=7, color='#666666', zorder=10)
    return note


def subset_for_dialog(spectra):
    """dialog_subset() with the tool-window limit from the preferences
    (View -> Plotting many spectra...). Returns (spectra to draw, total)."""
    try:
        from src.controllers.visualization.large_plot_controller import dialog_draw_limit
        limit = dialog_draw_limit()
    except Exception:
        limit = DEFAULT_DIALOG_COUNT
    return dialog_subset(spectra, limit)


LEGEND_MAX_ENTRIES = 30


def legend_if_few(ax, **kwargs):
    """ax.legend(**kwargs) only when the axes has at most LEGEND_MAX_ENTRIES
    labelled lines: a legend of hundreds of spectra (placed with 'best',
    which tries every position) takes seconds and cannot be read."""
    handles, labels = ax.get_legend_handles_labels()
    if 0 < len(labels) <= LEGEND_MAX_ENTRIES:
        return ax.legend(**kwargs)
    return None
