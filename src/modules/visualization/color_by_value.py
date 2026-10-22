# src/modules/visualization/color_by_value.py
"""Colour the spectra by a value (Line colours > Colours by value, see
line_colours_controller.py): the lines of the Overlay, Waterfall and Grid plots
get their colour from a colour scale - by their order in the spectra list, by
a number in their name (e.g. the temperature in 'TBA_45C' or 'T=45.00C') or
by a number stored with them (metadata, e.g. the temperature of a JASCO .jwb
scan) - with a colour bar. Spectra without a value are drawn grey. Qt-free;
the window is src/views/dialogs/visualization/color_by_value_dialog.py."""

import re

import numpy as np

MODES = ('off', 'order', 'name', 'metadata')
MODE_TEXT = {
    'off': 'Off (the usual colours)',
    'order': 'Order in the spectra list',
    'name': 'A number in the spectrum name',
    'metadata': 'A value stored with the spectra (metadata)',
}
COLORMAPS = ('viridis', 'plasma', 'inferno', 'cividis', 'coolwarm', 'RdBu_r', 'turbo',
             'rainbow', 'jet', 'Blues', 'Reds')
DEFAULT_SETTINGS = {'mode': 'off', 'number': -1, 'metadata_key': '', 'colormap': 'viridis',
                    'reverse': False, 'colorbar': True}
NO_VALUE_COLOR = '#B0B0B0'
PLOT_TYPES = ('Overlay plot', 'Waterfall plot', 'Grid plot')

# Numbers stored by the program for itself, not properties of the sample.
_INTERNAL_KEYS = {'column_index', 'valid_points', 'output_index', 'output_count',
                  'source_spectra_count', 'component_index', 'n_components', 'row', 'col',
                  'pixel_index', 'unique_id'}



def normalized(settings=None):
    s = dict(DEFAULT_SETTINGS)
    s.update({k: v for k, v in (settings or {}).items() if k in DEFAULT_SETTINGS})
    if s['mode'] not in MODES:
        s['mode'] = 'off'
    if s['colormap'] not in COLORMAPS:
        s['colormap'] = 'viridis'
    try:
        s['number'] = int(s['number'])
    except (TypeError, ValueError):
        s['number'] = -1
    s['reverse'], s['colorbar'] = bool(s['reverse']), bool(s['colorbar'])
    return s


def is_active(settings):
    return normalized(settings)['mode'] != 'off'


def numbers_in(name):
    """The numbers written in a spectrum name, from left to right:
    'TBA_45C : 0003' -> [45, 3]; 'CD [mdeg] T=10.04C' -> [10.04];
    'pH 7,4' -> [7.4] (a decimal comma between digits counts)."""
    out = []
    for m in re.finditer(r'\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?', str(name)):
        text = m.group(0).replace(',', '.')
        start = m.start()
        if start > 0 and str(name)[start - 1] == '-' and (start == 1 or not str(name)[start - 2].isalnum()):
            text = '-' + text                                  # 'T = -5' (not 'run-5')
        try:
            out.append(float(text))
        except ValueError:
            pass
    return out


def name_number_choices(spectra):
    """[(index, text)] for 'which number of the name': the last, then the
    first, second, ... up to the most numbers any name has."""
    most = max((len(numbers_in(s.get('label', ''))) for s in spectra), default=0)
    return [(-1, 'the last number')] + [(i, f"the {_ordinal(i)} number") for i in range(most)]


def _ordinal(i):
    words = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth']
    return words[i] if i < len(words) else f"{i + 1}th"


def metadata_keys(spectra):
    """Names of the numbers stored with the spectra (e.g. 'temperature_C'),
    in the order they first appear."""
    keys = []
    for s in spectra:
        for k, v in (s.get('metadata') or {}).items():
            if k in keys or k in _INTERNAL_KEYS or isinstance(v, bool):
                continue
            if isinstance(v, (int, float, np.integer, np.floating)) and np.isfinite(float(v)):
                keys.append(k)
    return keys


def value_of(spectrum, index, settings):
    """The value of one spectrum (index = its place in the list), or None."""
    s = normalized(settings)
    if s['mode'] == 'order':
        return float(index + 1)
    if s['mode'] == 'name':
        nums = numbers_in(spectrum.get('label', ''))
        try:
            return nums[s['number']]
        except IndexError:
            return None
    if s['mode'] == 'metadata':
        v = (spectrum.get('metadata') or {}).get(s['metadata_key'])
        if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
            return None
        return float(v) if np.isfinite(float(v)) else None
    return None


def values(spectra, settings):
    return [value_of(sp, i, settings) for i, sp in enumerate(spectra)]


def label(settings):
    """Title of the colour bar."""
    s = normalized(settings)
    if s['mode'] == 'order':
        return 'Order in the spectra list'
    if s['mode'] == 'name':
        which = 'last' if s['number'] < 0 else _ordinal(s['number'])
        return f"Number in the name ({which})"
    if s['mode'] == 'metadata':
        return s['metadata_key']
    return ''


def colour_scale(vals, settings):
    """(cmap, norm) for the values (None when no spectrum has one)."""
    import matplotlib
    from matplotlib.colors import Normalize
    s = normalized(settings)
    known = [v for v in vals if v is not None]
    if not known:
        return None, None
    lo, hi = min(known), max(known)
    if lo == hi:
        lo, hi = lo - 0.5, hi + 0.5
    cmap = matplotlib.colormaps[s['colormap']]
    if s['reverse']:
        cmap = cmap.reversed()
    return cmap, Normalize(lo, hi)


def colours(vals, settings):
    """A colour (hex) for every value; grey where there is no value."""
    from matplotlib.colors import to_hex
    cmap, norm = colour_scale(vals, settings)
    if cmap is None:
        return [NO_VALUE_COLOR] * len(vals)
    return [NO_VALUE_COLOR if v is None else to_hex(cmap(norm(v))) for v in vals]


def add_colorbar(figure, vals, settings):
    """A colour bar next to the plot(s) of *figure*; returns it (or None)."""
    from matplotlib.cm import ScalarMappable
    s = normalized(settings)
    cmap, norm = colour_scale(vals, settings)
    if not s['colorbar'] or cmap is None:
        return None
    axes = [ax for ax in figure.axes if ax.get_label() != '<colorbar>']
    if not axes:
        return None
    mappable = ScalarMappable(norm=norm, cmap=cmap)
    mappable.set_array([])
    return figure.colorbar(mappable, ax=axes, label=label(settings), fraction=0.04, pad=0.02)
