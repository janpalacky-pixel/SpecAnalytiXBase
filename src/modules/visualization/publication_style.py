# src/modules/visualization/publication_style.py
"""The look of the picture in Save plot for publication (Qt-free): font,
axis titles, ranges, ticks, frame, grid, the spectra's colours / line
styles / markers (all at once or each one), the legend's columns / frame /
title and a heatmap's colour map. Every choice starts as "as in the plot"
(STYLE_DEFAULTS): only what is changed is applied - on the copy made by
publication_figure.copy_for_publication, never on the plot on the screen.
Works for every plot type: one plot (Overlay, Waterfall, Mean ± SD ...),
several (Grid plot) and pictures with a colour bar (Heatmap)."""

KEEP = 'keep'                       # "as in the plot"
# marks a tool window puts on its plot (set on a copy by
# src/views/publication_actions.py): each kind can be left out of the picture
MAP_PIXEL_GID = 'sax_map_pixel'     # 2D Map: the + of the clicked pixel
MAP_ROI_GID = 'sax_map_roi'         # 2D Map: the outlines of the regions (ROI)
MAP_REF_GID = 'sax_map_ref'         # 2D Map: the numbered reference pixels
RANGE_GID = 'sax_range'             # a spectrum's shaded range (what the map is made of)
# {gid: (style key, what it is - for the window)}
MARKS = {MAP_PIXEL_GID: ('map_pixel', "The clicked pixel (+)"),
         MAP_ROI_GID: ('map_rois', "Regions (ROI outlines)"),
         MAP_REF_GID: ('map_refs', "Reference pixels (numbered circles)"),
         RANGE_GID: ('ranges', "Shaded range")}
CURSOR_GIDS = ('sax_cursor', 'sax_cursor_pinned', 'sax_band') + tuple(MARKS)

STYLE_DEFAULTS = {
    'font_family': '',              # '' = as in the plot
    'x_title': '', 'y_title': '',   # '' = as in the plot
    'title_mode': KEEP, 'title_text': '',
    'x_min': None, 'x_max': None, 'y_min': None, 'y_max': None,
    'x_dir': KEEP,                  # keep / increasing / decreasing
    'x_step': 0.0, 'y_step': 0.0,   # 0 = automatic
    'minor_ticks': KEEP,            # keep / on / off
    'tick_dir': KEEP,               # keep / out / in / inout
    'tick_len': 0.0,                # 0 = as in the plot (points)
    'mirror_ticks': KEEP,           # keep / on / off: ticks also on top and right
    'frame': KEEP,                  # keep / box / open
    'frame_pt': 0.0,                # 0 = as in the plot
    'plot_as': KEEP,                # keep / lines / points / both
    'marker': 'o', 'marker_size': 3.0,
    'marker_every': 1,              # a marker on every n-th point
    'palette': KEEP,
    'series': [],                   # [{show, name, color, style, width, marker}] by position
    'grid': KEEP,                   # keep / off / major / both
    'grid_axis': 'both', 'grid_color': '#b0b0b0', 'grid_style': '-', 'grid_pt': 0.5,
    'legend_ncol': 0,               # 0 = automatic
    'legend_frame': KEEP,           # keep / on / off
    'legend_title': '',
    'cmap': KEEP, 'c_min': None, 'c_max': None, 'cbar_label': '',
    # sizes of each kind of text (0 = automatic: from Text size)
    'axis_title_pt': 0.0, 'tick_pt': 0.0, 'legend_pt': 0.0, 'title_pt': 0.0,
    'band_pt': 0.0, 'cursor_pt': 0.0,              # band markers' labels, pinned cursors
    'x_numbers': KEEP, 'y_numbers': KEEP,          # keep / on / off: the numbers of an axis
    'band_labels': KEEP,                           # keep / off: the band markers' labels
    'band_rotation': KEEP,                         # keep / horizontal / vertical
    'band_lines': KEEP,                            # keep / off: the band markers' lines
    'cursors': KEEP,                               # keep / off: the pinned cursors
    # keep / off: the marks of a tool window's plot (MARKS)
    'map_pixel': KEEP, 'map_rois': KEEP, 'map_refs': KEEP, 'ranges': KEEP,
}

BAND_GID = 'sax_band'               # band markers' lines and labels
NOTE_GID = 'sax_note'               # the user's own labels, text and arrows (prefix)
PINNED_GID = 'sax_cursor_pinned'

FONTS = ('Arial', 'Helvetica', 'Times New Roman', 'Calibri', 'Cambria', 'Georgia',
         'Verdana', 'DejaVu Sans', 'DejaVu Serif', 'Liberation Sans', 'Liberation Serif')
LINE_STYLES = (('-', 'solid ———'), ('--', 'dashed – – –'), (':', 'dotted · · ·'),
               ('-.', 'dash-dot –·–·'))
MARKERS = (('o', 'circle ●'), ('s', 'square ■'), ('^', 'triangle ▲'), ('v', 'triangle ▼'),
           ('D', 'diamond ◆'), ('x', 'cross ×'), ('+', 'plus +'), ('.', 'dot ·'))
CMAPS = ('viridis', 'cividis', 'plasma', 'inferno', 'magma', 'Greys', 'gray', 'Blues',
         'RdBu_r', 'coolwarm', 'seismic', 'jet', 'turbo')
OKABE_ITO = ('#000000', '#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00',
             '#CC79A7')
PALETTES = (('okabe_ito', "colour-blind safe (Okabe-Ito)"),
            ('tab10', "matplotlib's 10 colours"),
            ('black', "all black"),
            ('black_styles', "black, different line styles"),
            ('greys', "shades of grey"),
            ('viridis', "viridis (dark blue → yellow)"),
            ('cividis', "cividis (blue → yellow)"),
            ('plasma', "plasma (blue → yellow)"),
            ('coolwarm', "cool-warm (blue → red)"))


def installed_fonts():
    """The FONTS that are on this computer."""
    try:
        from matplotlib import font_manager
        have = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        have = set()
    return [f for f in FONTS if f in have]


def palette_colors(name, n):
    """n colours (hex) of the colour set `name` (PALETTES)."""
    from matplotlib import colormaps
    from matplotlib.colors import to_hex
    n = max(1, int(n))
    if name == 'okabe_ito':
        return [OKABE_ITO[i % len(OKABE_ITO)] for i in range(n)]
    if name == 'tab10':
        cmap = colormaps['tab10']
        return [to_hex(cmap(i % 10)) for i in range(n)]
    if name in ('black', 'black_styles'):
        return ['#000000'] * n
    if name == 'greys':
        return [to_hex((v, v, v)) for v in _spread(0.0, 0.7, n)]
    if name in ('viridis', 'cividis', 'plasma', 'coolwarm'):
        cmap = colormaps[name]
        top = 0.9 if name in ('viridis', 'cividis', 'plasma') else 1.0
        return [to_hex(cmap(v)) for v in _spread(0.0, top, n)]
    return ['#000000'] * n


def _spread(lo, hi, n):
    if n == 1:
        return [lo]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


# ---------------------------------------------------------------- reading the plot
def _plot_axes(figure):
    return [ax for ax in figure.axes if not hasattr(ax, '_colorbar') and ax.get_visible()]


def data_lines(ax):
    """The spectra's lines of a plot (not band markers, cursors, ...)."""
    out = []
    for line in ax.get_lines():
        label = str(line.get_label())
        if label.startswith('_') or line.get_gid() in CURSOR_GIDS:
            continue
        out.append(line)
    return out


def series(figure):
    """[{label, color, style, width, marker}] of every spectrum drawn (each
    name once, in the order drawn)."""
    from matplotlib.colors import to_hex
    seen, out = set(), []
    for ax in _plot_axes(figure):
        for line in data_lines(ax):
            label = str(line.get_label())
            if label in seen:
                continue
            seen.add(label)
            try:
                color = to_hex(line.get_color())
            except Exception:
                color = '#000000'
            marker = line.get_marker()
            out.append({'label': label, 'color': color, 'style': line.get_linestyle(),
                        'width': float(line.get_linewidth()),
                        'marker': '' if marker in (None, 'None', '', ' ') else str(marker)})
    return out


def current(figure):
    """What the plot has now: {x_title, y_title, title, x_range, y_range,
    has_lines, has_colours} - shown as hints in the window."""
    axes = _plot_axes(figure)
    info = {'x_title': '', 'y_title': '', 'title': '', 'x_range': None, 'y_range': None,
            'has_lines': False, 'has_colours': bool(_mappables(figure)),
            'has_legend': any(ax.get_legend() is not None for ax in figure.axes),
            'has_bands': False, 'has_cursors': False, 'has_notes': False,
            'marks': []}                # the MARKS gids the plot has, in MARKS' order
    found = set()
    for ax in figure.axes:
        for a in list(ax.texts) + list(ax.get_lines()):
            gid = str(a.get_gid() or '')
            info['has_bands'] |= gid == BAND_GID
            info['has_cursors'] |= gid == PINNED_GID
            info['has_notes'] |= gid.startswith(NOTE_GID)
        for a in ax.get_children():
            gid = getattr(a, 'get_gid', lambda: None)()
            if gid in MARKS and a.get_visible():
                found.add(gid)
    info['marks'] = [g for g in MARKS if g in found]
    if not axes:
        return info
    ax = axes[0]
    info['x_title'] = next((a.get_xlabel() for a in axes if a.get_xlabel()), '')
    info['y_title'] = next((a.get_ylabel() for a in axes if a.get_ylabel()), '')
    info['title'] = next((a.get_title() for a in axes if a.get_title()), '')
    info['x_range'] = tuple(sorted(float(v) for v in ax.get_xlim()))
    info['y_range'] = tuple(sorted(float(v) for v in ax.get_ylim()))
    info['has_lines'] = any(data_lines(a) for a in axes)
    return info


def _mappables(figure):
    """Images / colour meshes of the plots (a heatmap, a 2D map)."""
    out = []
    for ax in _plot_axes(figure):
        out += list(ax.images)
        for c in ax.collections:
            try:
                if c.get_array() is not None and hasattr(c, 'set_cmap'):
                    out.append(c)
            except Exception:
                pass
    return out


# ---------------------------------------------------------------- changing the copy
def style_of(choices):
    """STYLE_DEFAULTS updated with the known keys of `choices`."""
    s = dict(STYLE_DEFAULTS)
    for k in STYLE_DEFAULTS:
        if choices and k in choices:
            s[k] = choices[k]
    return s


def apply_style(copy, style):
    """Change the copy as `style` asks. Returns ({full name: legend name},
    {full names hidden}) for the legend, which is made afterwards."""
    s = style_of(style)
    axes = _plot_axes(copy)
    _titles(copy, axes, s)
    for ax in axes:
        _ranges(ax, s)
        _ticks(ax, s)
        _frame(ax, s)
        _grid(ax, s)
    names, hidden = _lines(copy, axes, s)
    _colours(copy, s)
    return names, hidden


def legend_extras(style):
    """Keyword arguments for ax.legend from the style (columns, frame,
    title)."""
    s = style_of(style)
    kw = {}
    if int(s['legend_ncol'] or 0) > 0:
        kw['ncol'] = int(s['legend_ncol'])
    if s['legend_frame'] in ('on', 'off'):
        kw['frameon'] = s['legend_frame'] == 'on'
    if s['legend_title']:
        kw['title'] = s['legend_title']
    return kw


def set_font(text, style):
    family = style_of(style)['font_family']
    if family:
        text.set_fontfamily(family)


def _titles(copy, axes, s):
    from matplotlib.ticker import ScalarFormatter
    for key, get, set_, axis in (('x_title', 'get_xlabel', 'set_xlabel', 'xaxis'),
                                 ('y_title', 'get_ylabel', 'set_ylabel', 'yaxis')):
        text = s[key]
        if not text:
            continue
        # where the plots have a title (a Grid plot: e.g. only the bottom ones); else
        # on axes with numbers - not on a heatmap's names of the spectra
        numeric = [ax for ax in axes
                   if isinstance(getattr(ax, axis).get_major_formatter(), ScalarFormatter)]
        labelled = [ax for ax in numeric if getattr(ax, get)()]
        for ax in labelled or numeric:
            getattr(ax, set_)(text)
    if s['title_mode'] == 'hide':
        for ax in axes:
            ax.set_title('')
        if getattr(copy, '_suptitle', None) is not None:
            copy._suptitle.set_text('')
    elif s['title_mode'] == 'own' and s['title_text']:
        if len(axes) == 1:
            axes[0].set_title(s['title_text'])
        else:                                     # several plots: one title above them
            copy.suptitle(s['title_text'])


def _num(v):
    try:
        return None if v is None or v == '' else float(v)
    except (TypeError, ValueError):
        return None


def _ranges(ax, s):
    for lo_key, hi_key, get, set_, inverted, axis in (
            ('x_min', 'x_max', ax.get_xlim, ax.set_xlim, ax.xaxis_inverted, 'x'),
            ('y_min', 'y_max', ax.get_ylim, ax.set_ylim, ax.yaxis_inverted, 'y')):
        lo, hi = _num(s[lo_key]), _num(s[hi_key])
        if lo is None and hi is None:
            continue
        a, b = sorted(get())
        lo = a if lo is None else lo
        hi = b if hi is None else hi
        if lo == hi:
            continue
        lo, hi = sorted((lo, hi))
        set_((hi, lo) if inverted() else (lo, hi))
    if s['x_dir'] in ('increasing', 'decreasing'):
        want = s['x_dir'] == 'decreasing'
        if ax.xaxis_inverted() != want:
            ax.invert_xaxis()


def _ticks(ax, s):
    from matplotlib.ticker import AutoMinorLocator, MultipleLocator, NullLocator
    for axis, key, lim in ((ax.xaxis, 'x_step', ax.get_xlim()),
                           (ax.yaxis, 'y_step', ax.get_ylim())):
        step = _num(s[key]) or 0.0
        if step > 0 and axis.get_scale() == 'linear' and abs(lim[1] - lim[0]) / step <= 200:
            axis.set_major_locator(MultipleLocator(step))
        if s['minor_ticks'] == 'on' and axis.get_scale() == 'linear':
            axis.set_minor_locator(AutoMinorLocator())
        elif s['minor_ticks'] == 'off':
            axis.set_minor_locator(NullLocator())
    kw = {}
    if s['tick_dir'] in ('in', 'out', 'inout'):
        kw['direction'] = s['tick_dir']
    if s['mirror_ticks'] in ('on', 'off'):
        on = s['mirror_ticks'] == 'on'
        kw.update(top=on, right=on)
    if kw:
        ax.tick_params(axis='both', which='both', **kw)
    length = _num(s['tick_len']) or 0.0
    if length > 0:
        ax.tick_params(axis='both', which='major', length=length)
        ax.tick_params(axis='both', which='minor', length=length * 0.6)
    width = _num(s['frame_pt']) or 0.0
    if width > 0:
        ax.tick_params(axis='both', which='both', width=width)


def _frame(ax, s):
    if s['frame'] == 'box':
        for side in ('left', 'bottom', 'top', 'right'):
            ax.spines[side].set_visible(True)
    elif s['frame'] == 'open':
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        if s['mirror_ticks'] != 'on':
            ax.tick_params(axis='both', which='both', top=False, right=False)
    width = _num(s['frame_pt']) or 0.0
    if width > 0:
        for spine in ax.spines.values():
            spine.set_linewidth(width)


def _grid(ax, s):
    if s['grid'] == KEEP:
        return
    ax.grid(False, which='both')
    if s['grid'] == 'off':
        return
    kw = dict(color=s['grid_color'] or '#b0b0b0', linestyle=s['grid_style'] or '-',
              linewidth=_num(s['grid_pt']) or 0.5)
    axis = s['grid_axis'] if s['grid_axis'] in ('x', 'y') else 'both'
    ax.grid(True, which='major', axis=axis, **kw)
    if s['grid'] == 'both':
        from matplotlib.ticker import AutoMinorLocator
        for a in ((ax.xaxis,) if axis == 'x' else (ax.yaxis,) if axis == 'y'
                  else (ax.xaxis, ax.yaxis)):
            if a.get_scale() == 'linear' and s['minor_ticks'] != 'off':
                a.set_minor_locator(AutoMinorLocator())
        minor = dict(kw, linewidth=kw['linewidth'] * 0.5)
        ax.grid(True, which='minor', axis=axis, **minor)


def _lines(copy, axes, s):
    order = [d['label'] for d in series(copy)]
    index = {label: i for i, label in enumerate(order)}
    colours = palette_colors(s['palette'], len(order)) if s['palette'] != KEEP else None
    styles = [st for st, _ in LINE_STYLES]
    rows = list(s['series'] or [])
    names, hidden = {}, set()
    for ax in axes:
        for line in data_lines(ax):
            label = str(line.get_label())
            i = index.get(label, 0)
            if colours is not None:
                line.set_color(colours[i])
                if s['palette'] == 'black_styles':
                    line.set_linestyle(styles[i % len(styles)])
            if s['plot_as'] == 'lines':
                line.set_marker('None')
                if line.get_linestyle() in ('None', '', ' '):
                    line.set_linestyle('-')
            elif s['plot_as'] in ('points', 'both'):
                line.set_marker(s['marker'] or 'o')
                line.set_markersize(_num(s['marker_size']) or 3.0)
                line.set_markevery(max(1, int(_num(s['marker_every']) or 1)))
                if s['plot_as'] == 'points':
                    line.set_linestyle('None')
                elif line.get_linestyle() in ('None', '', ' '):
                    line.set_linestyle('-')
            row = rows[i] if i < len(rows) and isinstance(rows[i], dict) else {}
            if row.get('color'):
                line.set_color(row['color'])
            if row.get('style'):
                line.set_linestyle(row['style'])
            if _num(row.get('width')):
                line.set_linewidth(_num(row['width']))
            if 'marker' in row and row['marker'] is not None:
                line.set_marker(row['marker'] or 'None')
                if row['marker']:
                    line.set_markersize(_num(s['marker_size']) or 3.0)
                    line.set_markevery(max(1, int(_num(s['marker_every']) or 1)))
            if row.get('show') is False:
                line.set_visible(False)
                hidden.add(label)
            if row.get('name'):
                names[label] = row['name']
    return names, hidden


def _colours(copy, s):
    maps = _mappables(copy)
    if not maps:
        return
    lo, hi = _num(s['c_min']), _num(s['c_max'])
    for m in maps:
        if s['cmap'] != KEEP:
            try:
                m.set_cmap(s['cmap'])
            except Exception:
                pass
        if lo is not None or hi is not None:
            try:
                a, b = m.get_clim()
                m.set_clim(a if lo is None else lo, b if hi is None else hi)
            except Exception:
                pass
    for ax in copy.axes:                          # the colour bar follows (its link to
        bar = getattr(ax, '_colorbar', None)      # the picture is not kept in a copy)
        if bar is None:
            continue
        try:
            bar.update_normal(bar.mappable)
        except Exception:
            pass
        if s['cbar_label']:
            try:
                bar.set_label(s['cbar_label'])
            except Exception:
                pass


# ---------------------------------------------------------------- text sizes, labels, moving
def apply_texts(copy, style, font_pt=None):
    """After every text got Text size: the sizes asked for each kind of text,
    the axes' numbers shown or hidden, the band markers' and pinned cursors'
    look."""
    s = style_of(style)
    axis_pt, tick_pt = _num(s['axis_title_pt']), _num(s['tick_pt'])
    title_pt = _num(s['title_pt'])
    band_pt, cursor_pt = _num(s['band_pt']), _num(s['cursor_pt'])
    for ax in copy.axes:
        if axis_pt:
            ax.xaxis.label.set_fontsize(axis_pt)
            ax.yaxis.label.set_fontsize(axis_pt)
        if tick_pt:
            ax.tick_params(axis='both', which='both', labelsize=tick_pt)
            ax.xaxis.offsetText.set_fontsize(tick_pt)
            ax.yaxis.offsetText.set_fontsize(tick_pt)
        if title_pt:
            ax.title.set_fontsize(title_pt)
        if hasattr(ax, '_colorbar'):
            continue
        if s['x_numbers'] in ('on', 'off'):
            on = s['x_numbers'] == 'on'
            ax.tick_params(axis='x', which='both', labelbottom=on)
            ax.xaxis.offsetText.set_visible(on)
        if s['y_numbers'] in ('on', 'off'):
            on = s['y_numbers'] == 'on'
            ax.tick_params(axis='y', which='both', labelleft=on)
            ax.yaxis.offsetText.set_visible(on)
        for t in ax.texts:
            gid = str(t.get_gid() or '')
            if band_pt and gid == BAND_GID:
                t.set_fontsize(band_pt)
            if cursor_pt and gid == PINNED_GID:
                t.set_fontsize(cursor_pt)
            if gid == BAND_GID:
                if s['band_labels'] == 'off':
                    t.set_visible(False)
                if s['band_rotation'] in ('horizontal', 'vertical'):
                    t.set_rotation(0 if s['band_rotation'] == 'horizontal' else 90)
            if gid == PINNED_GID and s['cursors'] == 'off':
                t.set_visible(False)
        for line in ax.get_lines():
            gid = str(line.get_gid() or '')
            if gid == BAND_GID and s['band_lines'] == 'off':
                line.set_visible(False)
            if gid == PINNED_GID and s['cursors'] == 'off':
                line.set_visible(False)
        for a in ax.get_children():                # a tool window's marks left out
            gid = getattr(a, 'get_gid', lambda: None)()
            if gid in MARKS and s[MARKS[gid][0]] == 'off':
                a.set_visible(False)
    if title_pt and getattr(copy, '_suptitle', None) is not None:
        copy._suptitle.set_fontsize(title_pt)


def movable_texts(figure):
    """{key: text} of the texts that can be dragged in the preview: the
    titles ('title:<axes>', 'suptitle'), band markers' labels ('band:<axes>:<n>'),
    pinned cursors' numbers ('pinned:<axes>:<n>') and the user's own labels
    ('note:<axes>:<n>') - visible and with text."""
    out = {}
    sup = getattr(figure, '_suptitle', None)
    if sup is not None and sup.get_text() and sup.get_visible():
        out['suptitle'] = sup
    for i, ax in enumerate(figure.axes):
        if not ax.get_visible():
            continue
        if ax.title.get_text() and ax.title.get_visible():
            out[f'title:{i}'] = ax.title
        counts = {}
        for t in ax.texts:
            gid = str(t.get_gid() or '')
            kind = ('band' if gid == BAND_GID else 'pinned' if gid == PINNED_GID
                    else 'note' if gid.startswith(NOTE_GID) else None)
            arrow = getattr(t, 'arrow_patch', None) is not None
            if kind is None or not t.get_visible() or not (t.get_text() or arrow):
                continue
            if kind == 'note':                     # your labels: by their own number
                try:
                    n = int(gid.split(':')[1])
                except (IndexError, ValueError):
                    continue
            else:
                n = counts.get(kind, 0)
                counts[kind] = n + 1
            out[f'{kind}:{i}:{n}'] = t
    return out


def move_texts(copy, moved):
    """Shift the texts named in `moved` {key: (dx, dy) in points (y up)}."""
    if not moved:
        return
    from matplotlib.text import Annotation
    from matplotlib.transforms import ScaledTranslation
    texts = movable_texts(copy)
    titles = [k for k in moved if (k.startswith('title:') or k == 'suptitle') and k in texts]
    if titles:
        # a title moves exactly as dragged: the layout is made once and kept (else
        # the plot would grow into the title's old place), and the title is not
        # put back above the axes when drawn
        try:
            copy.draw_without_rendering()
            copy.set_layout_engine('none')
        except Exception:
            pass
        for key in titles:
            if key.startswith('title:'):
                texts[key].set_position(texts[key].get_position())
                copy.axes[int(key.split(':')[1])]._autotitlepos = False
    for key, (dx, dy) in moved.items():
        t = texts.get(key)
        if t is None:
            continue
        if isinstance(t, Annotation) and t.anncoords == 'offset points':
            x, y = t.xyann
            t.xyann = (x + dx, y + dy)
        elif isinstance(t, Annotation):
            continue
        else:
            t.set_transform(t.get_transform() +
                            ScaledTranslation(dx / 72.0, dy / 72.0, copy.dpi_scale_trans))

