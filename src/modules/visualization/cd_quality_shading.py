# src/modules/visualization/cd_quality_shading.py
"""Grey shading of the wavelengths where a plotted CD spectrum is
unreliable (detector got too little light) -- see
src/modules/data_io/cd_quality.py for the rule and the stored data.

Drawn on top of an already finished plot (main window and "Open in New
Window"), so none of the plot modes needs to know about it.
"""

import matplotlib.transforms as mtransforms

from src.modules.data_io.cd_quality import (
    clip_ranges, is_valid_quality, merge_ranges, unreliable_ranges)

SHADE_GID = 'cd_quality'
SHADE_COLOR = '0.45'
SHADE_ALPHA = 0.15
NO_SHADING_PLOT_TYPES = ('Heatmap',)


def _metadata(spectrum):
    if isinstance(spectrum, dict):
        return spectrum.get('metadata') or {}
    return getattr(spectrum, 'metadata', None) or {}


def _x(spectrum):
    return spectrum.get('x_scale', []) if isinstance(spectrum, dict) \
        else getattr(spectrum, 'x_scale', [])


def ranges_for_spectra(spectra, ht_limit, abs_limit):
    """Union of the unreliable ranges of *spectra*, each limited to that
    spectrum's own x range (so cropped spectra are not shaded beyond their
    data)."""
    pieces = []
    for spectrum in spectra:
        quality = _metadata(spectrum).get('cd_quality')
        if not is_valid_quality(quality):
            continue
        x = _x(spectrum)
        if len(x) == 0:
            continue
        x_min, x_max = float(min(x)), float(max(x))
        pieces.extend(clip_ranges(unreliable_ranges(quality, ht_limit, abs_limit),
                                  x_min, x_max))
    return merge_ranges(pieces)


def _plot_axes(fig):
    return [ax for ax in fig.axes
            if ax.get_visible() and ax.get_label() != '<colorbar>']


def apply_cd_quality_shading(fig, spectra, ht_limit, abs_limit, plot_type=''):
    """Shade unreliable CD regions in *fig*. Grid plot: axes i shows
    spectrum i; every other mode: one axes with all spectra. Returns the
    number of shaded regions drawn. Axis limits are left as they were."""
    if plot_type in NO_SHADING_PLOT_TYPES or fig is None:
        return 0
    axes = _plot_axes(fig)
    if not axes:
        return 0
    spectra = list(spectra or [])
    if plot_type == 'Grid plot':
        pairs = [(ax, [s]) for ax, s in zip(axes, spectra)]
    else:
        pairs = [(axes[0], spectra)]

    drawn = 0
    for ax, group in pairs:
        ranges = ranges_for_spectra(group, ht_limit, abs_limit)
        if not ranges:
            continue
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        auto_x, auto_y = ax.get_autoscalex_on(), ax.get_autoscaley_on()
        for lo, hi in ranges:
            ax.axvspan(lo, hi, color=SHADE_COLOR, alpha=SHADE_ALPHA, lw=0,
                       zorder=0, label='_nolegend_', gid=SHADE_GID)
            drawn += 1
        if len(pairs) == 1:
            lo, hi = max(ranges, key=lambda r: r[1] - r[0])
            ax.text(0.5 * (lo + hi), 0.98, 'CD unreliable\n(too little light)',
                    transform=mtransforms.blended_transform_factory(ax.transData, ax.transAxes),
                    ha='center', va='top', fontsize=7, color='0.35',
                    gid=SHADE_GID, clip_on=True, zorder=0.5)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_autoscalex_on(auto_x)
        ax.set_autoscaley_on(auto_y)
    return drawn
