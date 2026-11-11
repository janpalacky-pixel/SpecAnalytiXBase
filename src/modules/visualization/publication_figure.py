# src/modules/visualization/publication_figure.py
"""Save the plot for a publication (Qt-free): a copy of the figure in the
size of a journal column (in cm), with one text size for all labels, ticks
and the legend, lines at least as thick as asked, on white - saved as
TIFF / PNG (at the chosen dots per inch) or PDF / SVG / EPS (sharp at any
size). The figure on the screen is not changed."""

import io
import os
import pickle

from src.modules.visualization import publication_style as pst

CM = 1 / 2.54                                   # inches per cm

# Sizes (cm): a journal's columns (most journals: 8.3-9 cm, 11-14 cm,
# 17-18 cm; the height is kept), a page (inside margins of about 1.5 cm)
# and a slide.
# portrait / landscape as in Word and the printer's window; "full page": all
# of the page inside 1.5 cm margins; "half page": that width, about half its
# height (a plot in a report or a thesis). Shown as (W cm wide × H cm high).
SIZES = (("1 column", 8.5, None), ("1.5 columns", 11.4, None), ("2 columns", 17.5, None),
         ("A4 landscape, full page", 26.7, 18.0),
         ("A4 portrait, full page", 18.0, 26.7),
         ("A4 portrait, half page", 18.0, 13.5),
         ("A5 landscape, full page", 18.0, 11.8),
         ("Letter landscape, full page", 25.4, 18.6),
         ("Slide 16:9, full slide", 33.9, 19.1),
         ("Slide 4:3, full slide", 25.4, 19.1))


def size_text(name, width, height):
    """How a size is shown: "A4 landscape, full page (26.7 cm wide × 18 cm
    high)"; a column: "1 column (8.5 cm wide)"."""
    if height is None:
        return f"{name} ({width:g} cm wide)"
    return f"{name} ({width:g} cm wide \u00d7 {height:g} cm high)"
# the paper for printing (Printing tab): A4 unless another is chosen
PAPERS = (('A4', "A4 (21 × 29.7 cm)"), ('A5', "A5 (14.8 × 21 cm)"), ('A3', "A3 (29.7 × 42 cm)"),
          ('Letter', "Letter (21.6 × 27.9 cm)"))
COLUMNS = tuple((name, w) for name, w, h in SIZES[:3])
DPI_CHOICES = (300, 600, 1200)
FORMATS = (("TIFF", "tif"), ("PNG", "png"), ("PDF", "pdf"), ("SVG", "svg"), ("EPS", "eps"))
# at first: A4 landscape, full page (the user's wish 11-10: a plot printed or
# saved fills an A4 sheet), with text that reads well on a page; a journal's
# column is one choice away (Size: 1 column, Text size 7 pt) or a profile
DEFAULTS = {'width_cm': 26.7, 'height_cm': 18.0, 'dpi': 600, 'font_pt': 12.0, 'line_pt': 1.0,
            'legend': 'best', 'legend_place': 'inside', 'short_names': True,
            'print_fit': True, 'print_centre': True, 'print_grey': False, 'paper': 'A4',
            'print_orientation': 'auto', 'preview_fit': True}

# Where the legend goes; with 'inside' / 'outside' the plot (Best place:
# inside only). Outside, the corners are beside the plot (top or bottom).
LEGENDS = (("best", "Best place"), ("upper right", "Top right"), ("upper left", "Top left"),
           ("lower right", "Bottom right"), ("lower left", "Bottom left"),
           ("right", "Right"), ("left", "Left"), ("top", "Top"), ("bottom", "Bottom"),
           ("none", "No legend"))
PLACES = (("inside", "inside the plot"), ("outside", "outside the plot"))
_INSIDE = {'best': 'best', 'upper right': 'upper right', 'upper left': 'upper left',
           'lower right': 'lower right', 'lower left': 'lower left', 'right': 'center right',
           'left': 'center left', 'top': 'upper center', 'bottom': 'lower center'}
# outside: (legend's corner, point of the plot, the side it is pushed to)
_OUTSIDE = {'right': ('center left', (1, 0.5), 'right'),
            'upper right': ('upper left', (1, 1), 'right'),
            'lower right': ('lower left', (1, 0), 'right'),
            'left': ('center right', (0, 0.5), 'left'),
            'upper left': ('upper right', (0, 1), 'left'),
            'lower left': ('lower right', (0, 0), 'left'),
            'top': ('lower center', (0.5, 1), 'top'),
            'bottom': ('upper center', (0.5, 0), 'bottom')}
_GAP_PT = 3.0                                   # between the plot's labels and the legend
CURSOR_GID = 'sax_cursor'                       # the cursor that follows the mouse


def legend_choice(legend, place=None):
    """(position, 'inside'/'outside') - also from the choices of before
    ('inside', 'right' = right of the plot, 'below')."""
    old = {'inside': ('best', 'inside'), 'right': ('right', 'outside'),
           'below': ('bottom', 'outside')}
    if legend in old and place is None:
        return old[legend]
    legend = {'inside': 'best', 'below': 'bottom'}.get(legend, legend)
    if legend not in dict(LEGENDS):
        legend = 'best'
    if legend == 'best':
        place = 'inside'
    return legend, (place if place in ('inside', 'outside') else 'inside')


def _short_names(figure):
    """{full name: short name} of the spectrum names in the plot (legends,
    lines, titles, tick labels): the name of each spectrum without the name
    of its file ("raman_2comp_clean : raman_12" -> "raman_12") - when that
    still tells them apart."""
    names = []
    for ax in figure.axes:
        leg = ax.get_legend()
        if leg is not None:
            names += [t.get_text() for t in leg.get_texts()]
        names += [ln.get_label() for ln in ax.get_lines()
                  if not str(ln.get_label()).startswith('_')]
        names += [ax.get_title()]
        names += [t.get_text() for t in ax.get_yticklabels() + ax.get_xticklabels()]
    names = [n for n in dict.fromkeys(str(n) for n in names) if ' : ' in n]
    if not names:
        return {}
    short = {n: n.rsplit(' : ', 1)[1].strip() for n in names}
    if len(set(short.values())) == len(names) and all(short.values()):
        return short
    # spectra of several files with the same names (raman_01 in each): the file's
    # name kept, but only the part that tells the files apart
    # ("raman_2comp_clean : raman_01", "raman_2comp_noisy : raman_01" ->
    # "clean : raman_01", "noisy : raman_01")
    files = sorted({n.rsplit(' : ', 1)[0].strip() for n in names})
    lead = os.path.commonprefix(files)
    tail = os.path.commonprefix([f[::-1] for f in files])[::-1] if len(files) > 1 else ''
    cut = {}
    for f in files:
        part = f[len(lead):len(f) - len(tail)] if len(lead) + len(tail) < len(f) else f
        cut[f] = part.strip(' _-.') or f
    short = {n: f"{cut[n.rsplit(' : ', 1)[0].strip()]} : {n.rsplit(' : ', 1)[1].strip()}"
             for n in names}
    if len(set(short.values())) < len(names):
        return {}
    return short


def _shorten(text, short):
    for full in sorted(short, key=len, reverse=True):
        if full in text:
            text = text.replace(full, short[full])
    return text


def _ticks(ax, figure):
    """Not too many numbers on a small axis: about one every 1.2 cm."""
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
    box = ax.get_position()
    w_in, h_in = figure.get_size_inches()
    for axis, size_cm in ((ax.xaxis, box.width * w_in * 2.54), (ax.yaxis, box.height * h_in * 2.54)):
        if isinstance(axis.get_major_formatter(), ScalarFormatter) and axis.get_scale() == 'linear':
            axis.set_major_locator(MaxNLocator(nbins=max(3, int(size_cm / 1.2)),
                                               steps=[1, 2, 2.5, 5, 10]))


def copy_for_publication(figure, width_cm, height_cm, font_pt=None, line_pt=None,
                         legend='best', short_names=True, legend_place=None, legend_xy=None,
                         style=None, moved=None):
    """A copy of `figure` (the one on the screen stays as it is) in the size
    width_cm x height_cm: every text font_pt (titles 1 pt larger, the legend
    1 pt smaller), every data line at least line_pt thick (grid lines thin),
    not too many numbers on the axes, the legend where asked (LEGENDS, inside
    or outside the plot; legend_xy {axes number: (x, y)}: its bottom left
    corner moved there, in parts of the plot's width and height) with the
    short spectrum names; white background; without the cursor that follows
    the mouse; then the look asked in `style` (publication_style: font, axis
    titles, ranges, ticks, frame, grid, colours, the legend's columns, the
    size of each kind of text ...); `moved` {key: (dx, dy) points}: texts
    dragged in the preview (publication_style.movable_texts). None: kept as
    it is."""
    copy = pickle.loads(pickle.dumps(figure))
    copy.set_size_inches(width_cm * CM, height_cm * CM)
    copy.patch.set_facecolor('white')
    for ax in copy.axes:                           # not a part of the picture
        for a in list(ax.get_children()):
            if getattr(a, 'get_gid', lambda: None)() == CURSOR_GID:
                try:
                    a.remove()
                except Exception:
                    a.set_visible(False)
    position, place = legend_choice(legend, legend_place)
    short = _short_names(copy) if short_names else {}
    from matplotlib.text import Text
    titles = set()
    legend_pt = max(4.0, font_pt - 1) if font_pt else None
    if style and (pst._num(pst.style_of(style)['legend_pt']) or 0) > 0:
        legend_pt = pst._num(pst.style_of(style)['legend_pt'])
    legends = []                                   # made at the end (sizes known then)
    for i, ax in enumerate(copy.axes):
        titles.add(id(ax.title))
        if hasattr(ax, '_colorbar'):               # a colour bar: only its text size
            if font_pt:
                ax.tick_params(labelsize=font_pt)
            continue
        if font_pt:
            ax.tick_params(labelsize=font_pt)
        if line_pt:
            for line in ax.get_lines():
                if line.get_linewidth() < line_pt and line.get_linestyle() not in ('None', ''):
                    line.set_linewidth(line_pt)
        for grid in ax.get_xgridlines() + ax.get_ygridlines():
            grid.set_linewidth(min(grid.get_linewidth(), 0.5))
        _ticks(ax, copy)
        if short:                                  # e.g. the names of a heatmap's rows
            for get, set_ in ((ax.get_yticklabels, ax.set_yticklabels),
                              (ax.get_xticklabels, ax.set_xticklabels)):
                labels = [t.get_text() for t in get()]
                if any(l in short for l in labels):
                    ticks = ax.get_yticks() if get == ax.get_yticklabels else ax.get_xticks()
                    if set_ == ax.set_yticklabels:
                        ax.set_yticks(ticks)
                    else:
                        ax.set_xticks(ticks)
                    set_([short.get(l, l) for l in labels])
        leg = ax.get_legend()
        if leg is not None:
            texts = [t.get_text() for t in leg.get_texts()]
            handles = list(getattr(leg, 'legend_handles', None) or
                           getattr(leg, 'legendHandles', []))
            own_h, own_l = ax.get_legend_handles_labels()
            if own_l == texts:
                handles = own_h                    # the plotted lines themselves
            # spectra hidden with a click on the legend: not in the picture's legend
            gone = {str(l.get_label()) for l in ax.get_lines() if not l.get_visible()}
            if gone:
                kept = [(h, t) for h, t in zip(handles, texts) if t not in gone]
                handles, texts = [h for h, _ in kept], [t for _, t in kept]
            leg.remove()
            if position != 'none' and handles:
                legends.append((i, ax, handles, texts))
    renamed, hidden = pst.apply_style(copy, style) if style else ({}, set())
    if getattr(copy, '_suptitle', None) is not None:
        titles.add(id(copy._suptitle))
    legends = _legend_entries(legends, short, renamed, hidden)
    for text in copy.findobj(Text):
        if style:
            pst.set_font(text, style)
        if short and text.get_text():
            new = _shorten(text.get_text(), short)
            if new != text.get_text():
                text.set_text(new)
        if str(text.get_gid() or '').startswith(pst.NOTE_GID):
            continue                               # your own labels keep their own size
        if font_pt:
            if id(text) in titles:
                text.set_fontsize(font_pt + 1)
                text.set_wrap(True)
            else:
                text.set_fontsize(font_pt)
    if style:
        pst.apply_texts(copy, style, font_pt)
    _heatmap_defaults(copy, pst.style_of(style) if style else pst.STYLE_DEFAULTS)
    _fit_layout(copy)
    _fit_titles(copy)
    _add_legends(copy, legends, position, place, legend_pt, legend_xy or {}, width_cm,
                 style)
    pst.move_texts(copy, moved)                     # last: the layout is made then
    return copy


def _heatmap_defaults(copy, style):
    """A plot with a picture (a heatmap): no grid lines across it (unless a
    grid was chosen), and not more spectra's names on an axis than fit (every
    n-th name: one per text line)."""
    from matplotlib.ticker import FixedFormatter
    for ax in copy.axes:
        if hasattr(ax, '_colorbar') or not (ax.images or any(
                getattr(c, 'get_array', lambda: None)() is not None for c in ax.collections)):
            continue
        if style.get('grid', pst.KEEP) == pst.KEEP:
            ax.grid(False, which='both')
        box = ax.get_position()
        w_in, h_in = copy.get_size_inches()
        for axis, get_ticks, set_ticks, labels, room_pt in (
                (ax.yaxis, ax.get_yticks, ax.set_yticks, ax.get_yticklabels(),
                 box.height * h_in * 72),
                (ax.xaxis, ax.get_xticks, ax.set_xticks, ax.get_xticklabels(),
                 box.width * w_in * 72)):
            names = [t.get_text() for t in labels]
            if not names or not any(n and not _is_number(n) for n in names):
                continue                           # numbers: thinned elsewhere
            size = labels[0].get_fontsize() or 8
            if axis is ax.xaxis:
                size *= max(1, max(len(n) for n in names)) * 0.6   # names side by side
            fit = max(1, int(room_pt / (size * 1.25)))
            step = -(-len(names) // fit)
            if step > 1:
                ticks = list(get_ticks())
                keep = list(range(0, len(names), step))
                set_ticks([ticks[k] for k in keep])
                (ax.set_yticklabels if axis is ax.yaxis else ax.set_xticklabels)(
                    [names[k] for k in keep])


def _is_number(text):
    try:
        float(str(text).replace('\u2212', '-'))
        return True
    except ValueError:
        return False


def _fit_titles(copy):
    """A title longer than its plot (e.g. a heatmap's with its colour range)
    gets smaller to fit on one or two lines (not below 6 pt)."""
    titles = [ax.title for ax in copy.axes if ax.title.get_text() and ax.title.get_visible()]
    if not titles:
        return
    try:
        renderer = copy._get_renderer()
    except Exception:
        return
    for t in titles:
        ax = t.axes
        try:
            width = t.get_window_extent(renderer).width
        except Exception:
            continue
        room = ax.bbox.width * 2                   # up to two lines
        if width > room > 0:
            t.set_fontsize(max(6.0, t.get_fontsize() * room / width))


def _legend_entries(legends, short, renamed, hidden):
    """The legends with the spectra's lines themselves (their new colours),
    the names given (else the short names), without the hidden spectra."""
    out = []
    for i, ax, handles, texts in legends:
        own = {str(line.get_label()): line for line in pst.data_lines(ax)}
        hs, ns = [], []
        for handle, text in zip(handles, texts):
            if text in hidden:
                continue
            hs.append(own.get(text, handle))
            ns.append(renamed.get(text) or short.get(text, text))
        if hs:
            out.append((i, ax, hs, ns))
    return out


def _add_legends(copy, legends, position, place, legend_pt, legend_xy, width_cm,
                 style=None):
    if not legends:
        return
    extras = pst.legend_extras(style) if style else {}
    family = pst.style_of(style)['font_family'] if style else ''
    from matplotlib.transforms import offset_copy
    room = {}
    if place == 'outside' and any(i not in legend_xy for i, *_ in legends):
        room = _room_around(copy, [ax for _, ax, _, _ in legends])
    for i, ax, handles, names in legends:
        kw = {'fontsize': legend_pt} if legend_pt else {}
        if family:
            kw = {'prop': {'family': family, 'size': legend_pt}} if legend_pt \
                else {'prop': {'family': family}}
        kw.update(handlelength=1.5, borderpad=0.3, labelspacing=0.25)
        if i in legend_xy:                         # moved by the mouse
            kw.update(extras)
            x, y = legend_xy[i]
            new = ax.legend(handles, names, loc='lower left', bbox_to_anchor=(x, y),
                            bbox_transform=ax.transAxes, borderaxespad=0.0, **kw)
            new.set_in_layout(False)
        elif place == 'outside':
            corner, point, side = _OUTSIDE[position if position != 'best' else 'right']
            left, right, bottom, top = room.get(id(ax), (0.0, 0.0, 0.0, 0.0))
            dx = {'right': right + _GAP_PT, 'left': -(left + _GAP_PT)}.get(side, 0.0)
            dy = {'top': top + _GAP_PT, 'bottom': -(bottom + _GAP_PT)}.get(side, 0.0)
            if side in ('top', 'bottom'):
                kw['ncol'] = min(len(names), max(1, int(width_cm / 2.8)))
            kw.update(extras)
            new = ax.legend(handles, names, loc=corner, bbox_to_anchor=point,
                            bbox_transform=offset_copy(ax.transAxes, fig=copy, x=dx, y=dy,
                                                       units='points'),
                            borderaxespad=0.0, **kw)
        else:
            kw.update(extras)
            new = ax.legend(handles, names, loc=_INSIDE[position], **kw)
            new.set_in_layout(False)               # the plot keeps its size
        if legend_pt and new.get_title().get_text():
            new.get_title().set_fontsize(legend_pt)
        if family:
            new.get_title().set_fontfamily(family)
    if _tight(copy):
        _tight_layout(copy)


def _room_around(copy, axes):
    """{id(axes): (left, right, bottom, top)}: how far (points) the plot's
    numbers, labels and title reach beyond its frame on each side."""
    out = {}
    try:
        copy.draw_without_rendering()
        renderer = copy._get_renderer()
        scale = 72.0 / copy.dpi
        for ax in axes:
            tight, frame = ax.get_tightbbox(renderer), ax.bbox
            out[id(ax)] = (max(0.0, frame.x0 - tight.x0) * scale,
                           max(0.0, tight.x1 - frame.x1) * scale,
                           max(0.0, frame.y0 - tight.y0) * scale,
                           max(0.0, tight.y1 - frame.y1) * scale)
    except Exception:
        pass
    return out


def _tight(copy):
    engine = copy.get_layout_engine()
    return engine is not None and type(engine).__name__ == 'TightLayoutEngine' or \
        getattr(copy, '_sax_tight', False)


def _tight_layout(copy):
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            copy.tight_layout()
    except Exception:
        pass


def _fit_layout(copy):
    """Nothing cut off at the new size: the constrained layout - or, when a
    colour bar was added for another layout (it cannot be changed then),
    the tight layout once (again after the legend is added)."""
    if any(hasattr(ax, '_colorbar') for ax in copy.axes):
        engine = copy.get_layout_engine()
        if engine is not None and type(engine).__name__ == 'ConstrainedLayoutEngine':
            return                                  # already: it fits itself
        copy._sax_tight = True
        _tight_layout(copy)
        return
    try:
        copy.set_layout_engine('constrained')
    except Exception:
        pass


def _savefig(copy, target, **kwargs):
    """savefig; when the constrained layout cannot be made (e.g. a colour bar
    added in a way it does not know), the tight layout, else none."""
    try:
        copy.savefig(target, **kwargs)
        return
    except Exception:
        last = None
        for engine in ('tight', 'none'):
            try:
                copy.set_layout_engine(engine)
                if hasattr(target, 'seek'):
                    target.seek(0)
                    target.truncate()
                copy.savefig(target, **kwargs)
                return
            except Exception as exc:
                last = exc
        raise last


def _options(kw):
    """The keyword choices that copy_for_publication takes."""
    return {k: kw[k] for k in ('font_pt', 'line_pt', 'legend', 'short_names', 'legend_place',
                               'legend_xy', 'style', 'moved') if k in kw}


def save_for_publication(figure, path, width_cm, height_cm, dpi=600, font_pt=None,
                         line_pt=None, legend='best', short_names=True, **more):
    """Save the publication copy of `figure` to `path` (the format from its
    ending: .tif/.tiff, .png, .pdf, .svg, .eps). Returns the copy."""
    copy = copy_for_publication(figure, width_cm, height_cm, font_pt, line_pt, legend,
                                short_names, **_options(more))
    fmt = str(path).rsplit('.', 1)[-1].lower()
    kwargs = {'dpi': dpi, 'facecolor': 'white'}
    if fmt in ('tif', 'tiff'):
        kwargs['format'] = 'tiff'
        kwargs['pil_kwargs'] = {'compression': 'tiff_lzw'}
    _savefig(copy, path, **kwargs)
    return copy


def render(figure, width_cm, height_cm, dpi=100, **choices):
    """(PNG bytes, boxes) of the publication copy at dpi; boxes: [(axes
    number, legend box, plot frame)] of the legends and [(key, text box,
    None)] of the titles and labels (publication_style.movable_texts), in the
    picture's pixels (x0, y0, x1, y1 from its top left corner) - for moving
    them with the mouse."""
    copy = copy_for_publication(figure, width_cm, height_cm, **_options(choices))
    copy.set_dpi(dpi)
    buf = io.BytesIO()
    _savefig(copy, buf, format='png', dpi=dpi, facecolor='white')
    height = copy.bbox.height
    boxes = []
    for i, ax in enumerate(copy.axes):
        leg = ax.get_legend()
        if leg is None or not leg.get_visible():
            continue
        try:
            lb, fb = leg.get_window_extent(), ax.bbox
        except Exception:
            continue
        boxes.append((i, (lb.x0, height - lb.y1, lb.x1, height - lb.y0),
                      (fb.x0, height - fb.y1, fb.x1, height - fb.y0)))
    for key, text in pst.movable_texts(copy).items():   # titles and labels: draggable too
        try:
            tb = text.get_window_extent()
            arrow = getattr(text, 'arrow_patch', None)
            if (tb.width <= 0 or not text.get_text()) and arrow is not None:
                tb = arrow.get_window_extent()           # an arrow without text: the arrow
        except Exception:
            continue
        if tb.width > 0 and tb.height > 0:
            extra = None
            if key.startswith('note:'):            # to turn a move into the plot's units
                ax = copy.axes[int(key.split(':')[1])]
                fb = ax.bbox
                extra = {'frame': (fb.x0, height - fb.y1, fb.x1, height - fb.y0),
                         'xlim': tuple(ax.get_xlim()), 'ylim': tuple(ax.get_ylim()),
                         'xscale': ax.get_xscale(), 'yscale': ax.get_yscale()}
                if getattr(text, 'arrow_patch', None) is not None and \
                        getattr(text, 'anncoords', None) == 'data':
                    tip = ax.transData.transform(text.xy)      # an arrow: its two ends
                    tail = ax.transData.transform(text.xyann)
                    extra['tip'] = (float(tip[0]), float(height - tip[1]))
                    extra['tail'] = (float(tail[0]), float(height - tail[1]))
                    extra['text'] = bool(text.get_text())     # the box is its text's
            boxes.append((key, (tb.x0, height - tb.y1, tb.x1, height - tb.y0), extra))
    return buf.getvalue(), boxes


def pixel_to_data(extra, px, py):
    """A point of the picture (pixels from its top left) in the plot's
    units, with the plot's frame and ranges as render gives them."""
    import math
    x0, y0, x1, y1 = extra['frame']
    fx = (px - x0) / (x1 - x0)
    fy = (y1 - py) / (y1 - y0)
    out = []
    for f, (a, b), scale in ((fx, extra['xlim'], extra['xscale']),
                             (fy, extra['ylim'], extra['yscale'])):
        if scale == 'log' and a > 0 and b > 0:
            out.append(10 ** (math.log10(a) + f * (math.log10(b) - math.log10(a))))
        else:
            out.append(a + f * (b - a))
    return tuple(out)


def preview_png(figure, width_cm, height_cm, font_pt=None, line_pt=None, dpi=100,
                legend='best', short_names=True, **more):
    """The publication copy as PNG bytes (for a preview, or for printing)."""
    return render(figure, width_cm, height_cm, dpi, font_pt=font_pt, line_pt=line_pt,
                  legend=legend, short_names=short_names, **more)[0]


def moved_legend(legend_box, frame, dx, dy):
    """(x, y) of a legend's bottom left corner, in parts of the plot's width
    and height, after it was moved by (dx, dy) pixels (y down) - boxes as
    render gives them."""
    x0, y0, x1, y1 = legend_box
    fx0, fy0, fx1, fy1 = frame
    return ((x0 + dx - fx0) / (fx1 - fx0), (fy1 - (y1 + dy)) / (fy1 - fy0))


def print_place(page_w, page_h, pic_w, pic_h, fit=True, centre=True, caption_h=0.0):
    """(x, y, w, h) of the picture on the printed page (all in the printer's
    dots; the page = its printable part): fit = as large as the page lets
    it (the text grows with it), else its own size (made smaller only when
    larger than the page); centre = in the middle, else at the top left;
    caption_h = room kept under it for a caption line."""
    room_h = max(1.0, page_h - caption_h)
    scale = min(page_w / pic_w, room_h / pic_h)
    if not fit:
        scale = min(1.0, scale)
    w, h = pic_w * scale, pic_h * scale
    if centre:
        return (page_w - w) / 2, (room_h - h) / 2, w, h
    return 0.0, 0.0, w, h


def pixels(width_cm, height_cm, dpi):
    """(width, height) in pixels of a picture of this size at dpi."""
    return round(width_cm * CM * dpi), round(height_cm * CM * dpi)
