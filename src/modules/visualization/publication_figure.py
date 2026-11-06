# src/modules/visualization/publication_figure.py
"""Save the plot for a publication (Qt-free): a copy of the figure in the
size of a journal column (in cm), with one text size for all labels, ticks
and the legend, lines at least as thick as asked, on white - saved as
TIFF / PNG (at the chosen dots per inch) or PDF / SVG / EPS (sharp at any
size). The figure on the screen is not changed."""

import io
import pickle

CM = 1 / 2.54                                   # inches per cm

# Sizes (cm): a journal's columns (most journals: 8.3-9 cm, 11-14 cm,
# 17-18 cm; the height is kept), a page (inside margins of about 1.5 cm)
# and a slide.
SIZES = (("1 column", 8.5, None), ("1.5 columns", 11.4, None), ("2 columns", 17.5, None),
         ("A4 page, upright (its width)", 18.0, 13.5),
         ("A4 page, sideways (all of it)", 26.7, 18.0),
         ("A5 page, sideways (all of it)", 18.0, 11.8),
         ("Letter page, sideways (all of it)", 25.4, 18.6),
         ("Slide 16:9 (all of it)", 33.9, 19.1),
         ("Slide 4:3 (all of it)", 25.4, 19.1))
COLUMNS = tuple((name, w) for name, w, h in SIZES[:3])
DPI_CHOICES = (300, 600, 1200)
FORMATS = (("TIFF", "tif"), ("PNG", "png"), ("PDF", "pdf"), ("SVG", "svg"), ("EPS", "eps"))
DEFAULTS = {'width_cm': 8.5, 'height_cm': 6.5, 'dpi': 600, 'font_pt': 8.0, 'line_pt': 1.0,
            'legend': 'best', 'legend_place': 'inside', 'short_names': True,
            'print_fit': True, 'print_centre': True, 'print_grey': False,
            'preview_fit': True}

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
    short = {n: n.rsplit(' : ', 1)[1].strip() for n in names}
    if not names or len(set(short.values())) < len(names) or not all(short.values()):
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
                         legend='best', short_names=True, legend_place=None, legend_xy=None):
    """A copy of `figure` (the one on the screen stays as it is) in the size
    width_cm x height_cm: every text font_pt (titles 1 pt larger, the legend
    1 pt smaller), every data line at least line_pt thick (grid lines thin),
    not too many numbers on the axes, the legend where asked (LEGENDS, inside
    or outside the plot; legend_xy {axes number: (x, y)}: its bottom left
    corner moved there, in parts of the plot's width and height) with the
    short spectrum names; white background; without the cursor that follows
    the mouse. None: kept as it is."""
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
            leg.remove()
            if position != 'none' and handles:
                legends.append((i, ax, handles, [short.get(t, t) for t in texts]))
    for text in copy.findobj(Text):
        if short and text.get_text():
            new = _shorten(text.get_text(), short)
            if new != text.get_text():
                text.set_text(new)
        if font_pt:
            if id(text) in titles:
                text.set_fontsize(font_pt + 1)
                text.set_wrap(True)
            else:
                text.set_fontsize(font_pt)
    _fit_layout(copy)
    _add_legends(copy, legends, position, place, legend_pt, legend_xy or {}, width_cm)
    return copy


def _add_legends(copy, legends, position, place, legend_pt, legend_xy, width_cm):
    if not legends:
        return
    from matplotlib.transforms import offset_copy
    room = {}
    if place == 'outside' and any(i not in legend_xy for i, *_ in legends):
        room = _room_around(copy, [ax for _, ax, _, _ in legends])
    for i, ax, handles, names in legends:
        kw = {'fontsize': legend_pt} if legend_pt else {}
        kw.update(handlelength=1.5, borderpad=0.3, labelspacing=0.25)
        if i in legend_xy:                         # moved by the mouse
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
            new = ax.legend(handles, names, loc=corner, bbox_to_anchor=point,
                            bbox_transform=offset_copy(ax.transAxes, fig=copy, x=dx, y=dy,
                                                       units='points'),
                            borderaxespad=0.0, **kw)
        else:
            new = ax.legend(handles, names, loc=_INSIDE[position], **kw)
            new.set_in_layout(False)               # the plot keeps its size
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
                               'legend_xy') if k in kw}


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
    """(PNG bytes, legends) of the publication copy at dpi; legends: [(axes
    number, legend box, plot frame)] in the picture's pixels (x0, y0, x1, y1
    from its top left corner) - for moving a legend with the mouse."""
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
    return buf.getvalue(), boxes


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
