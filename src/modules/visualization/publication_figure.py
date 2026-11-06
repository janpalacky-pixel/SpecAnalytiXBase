# src/modules/visualization/publication_figure.py
"""Save the plot for a publication (Qt-free): a copy of the figure in the
size of a journal column (in cm), with one text size for all labels, ticks
and the legend, lines at least as thick as asked, on white - saved as
TIFF / PNG (at the chosen dots per inch) or PDF / SVG / EPS (sharp at any
size). The figure on the screen is not changed."""

import io
import pickle

CM = 1 / 2.54                                   # inches per cm

# Widths of a journal's columns (most journals: 8.3-9 cm, 11-14 cm, 17-18 cm)
COLUMNS = (("1 column", 8.5), ("1.5 columns", 11.4), ("2 columns", 17.5))
DPI_CHOICES = (300, 600, 1200)
FORMATS = (("TIFF", "tif"), ("PNG", "png"), ("PDF", "pdf"), ("SVG", "svg"), ("EPS", "eps"))
DEFAULTS = {'width_cm': 8.5, 'height_cm': 6.5, 'dpi': 600, 'font_pt': 8.0, 'line_pt': 1.0}


def copy_for_publication(figure, width_cm, height_cm, font_pt=None, line_pt=None):
    """A copy of `figure` (the one on the screen stays as it is) in the size
    width_cm x height_cm; every text font_pt (titles 1 pt larger), every line
    at least line_pt thick; white background. None: kept as it is."""
    copy = pickle.loads(pickle.dumps(figure))
    copy.set_size_inches(width_cm * CM, height_cm * CM)
    copy.patch.set_facecolor('white')
    if font_pt:
        from matplotlib.text import Text
        titles = set()
        for ax in copy.axes:
            titles.add(id(ax.title))
            ax.tick_params(labelsize=font_pt)
        for text in copy.findobj(Text):
            text.set_fontsize(font_pt + (1 if id(text) in titles else 0))
    if line_pt:
        from matplotlib.lines import Line2D
        for line in copy.findobj(Line2D):
            if line.get_linewidth() < line_pt and line.get_linestyle() not in ('None', ''):
                line.set_linewidth(line_pt)
    try:
        copy.set_layout_engine('constrained')    # nothing cut off at the new size
    except Exception:
        pass
    return copy


def save_for_publication(figure, path, width_cm, height_cm, dpi=600, font_pt=None,
                         line_pt=None):
    """Save the publication copy of `figure` to `path` (the format from its
    ending: .tif/.tiff, .png, .pdf, .svg, .eps). Returns the copy."""
    copy = copy_for_publication(figure, width_cm, height_cm, font_pt, line_pt)
    fmt = path.rsplit('.', 1)[-1].lower()
    kwargs = {'dpi': dpi, 'facecolor': 'white'}
    if fmt in ('tif', 'tiff'):
        kwargs['format'] = 'tiff'
        kwargs['pil_kwargs'] = {'compression': 'tiff_lzw'}
    copy.savefig(path, **kwargs)
    return copy


def preview_png(figure, width_cm, height_cm, font_pt=None, line_pt=None, dpi=100):
    """The publication copy as PNG bytes (for a preview on the screen)."""
    copy = copy_for_publication(figure, width_cm, height_cm, font_pt, line_pt)
    buf = io.BytesIO()
    copy.savefig(buf, format='png', dpi=dpi, facecolor='white')
    return buf.getvalue()


def pixels(width_cm, height_cm, dpi):
    """(width, height) in pixels of a picture of this size at dpi."""
    return round(width_cm * CM * dpi), round(height_cm * CM * dpi)
