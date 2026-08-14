# src/modules/utils/pdf_report_utils.py
"""
Shared PDF report export utility.

Used by every analysis dialog's "Export PDF" button (sitting next to the
existing "Export CSV" button) to produce a self-contained PDF summarizing
one run of an analysis: a title/metadata page (what was run, when, on
which spectra, with which settings), the dialog's own plot exactly as
currently shown, and the results table paginated as needed.

Built on matplotlib's PdfPages backend -- matplotlib is already a hard
dependency of this app (every plot in it uses matplotlib), so this adds
no new dependency, unlike a reportlab-based approach would.

IMPORTANT: the caller's live plot Figure (from its own canvas) is passed
in and embedded AS AN IMAGE -- rasterized via the figure's own savefig()
into an in-memory buffer, then placed onto a freshly-built, consistently
sized page. This module never resizes, re-styles, or calls tight_layout
on the caller's actual Figure object, since it's the same object still
attached to the dialog's on-screen canvas; mutating it here would visibly
change the user's live plot as a side effect of exporting a PDF. Rasterizing
also keeps every page in the report the same physical size regardless of
whatever size the dialog window happened to be on screen -- embedding a
live Figure object directly via pdf.savefig(figure) makes matplotlib size
that PDF page to the figure's OWN dimensions, which vary with the dialog's
window size and would otherwise produce a report with mismatched page
sizes from one page to the next.
"""
import datetime
import io
import textwrap

import matplotlib.image as mpimg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)

_ROWS_PER_PAGE = 32
_PAGE_SIZE = (11, 8.5)          # landscape, matches the figure/table pages
_TITLE_PAGE_SIZE = (8.5, 11)    # portrait, for the title/metadata page
_LIST_WRAP_CHARS = 100          # conservative chars-per-line at fontsize 8
                                 # on an 8.5in-wide page with ~0.85 usable
                                 # fraction -- see _add_title_page.
_META_WRAP_CHARS = 78           # same idea as _LIST_WRAP_CHARS but for the
                                 # Settings block, drawn at fontsize 10
                                 # (bigger font, so fewer characters fit per
                                 # line than the fontsize-8 spectra list).


def export_report_pdf(path, title, meta_lines=None, figure=None,
                      table_headers=None, table_rows=None, source_labels=None):
    """Write a PDF report to *path*.

    Args:
        path: output .pdf file path.
        title: report title (e.g. "Kinetics Fitting — single wavelength").
        meta_lines: list of strings for the "Settings" block on the title
            page (e.g. "Number of components: 2", "Confidence: 95%"). A
            generation timestamp is added automatically -- no need to
            include one.
        figure: an existing matplotlib Figure to embed (typically the
            dialog's own currently-displayed plot), on its own page.
            Rasterized, never modified -- see module docstring. Optional
            -- omit for a table-only report.
        table_headers: list of column header strings for the results
            table. Optional (omit for a plot-only report).
        table_rows: list of rows, each a list of strings matching
            table_headers (same length). Paginated automatically.
        source_labels: optional list of spectrum labels included in the
            analysis, listed on the title page for provenance.

    Raises on any failure -- callers show a message box on the exception
    rather than silently leaving a partial/corrupt file; PdfPages writes
    incrementally, so an exception partway through can leave a truncated
    file at *path*, which is why every dialog's Export PDF handler should
    catch and report rather than assume success.
    """
    meta_lines = list(meta_lines or [])
    with PdfPages(path) as pdf:
        _add_title_page(pdf, title, meta_lines, source_labels)
        if figure is not None:
            _add_existing_figure(pdf, figure)
        if table_headers:
            _add_table_pages(pdf, table_headers, table_rows or [])


def _add_title_page(pdf, title, meta_lines, source_labels):
    fig = Figure(figsize=_TITLE_PAGE_SIZE)
    ax = fig.add_subplot(111)
    ax.axis('off')

    y = 0.95
    ax.text(0.06, y, title, fontsize=18, fontweight='bold', color='#1565C0',
            transform=ax.transAxes, va='top')
    y -= 0.05
    ax.text(0.06, y, f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} "
            "— SpecAnalytiXBase", fontsize=9, color='#666',
            transform=ax.transAxes, va='top')
    y -= 0.05

    if meta_lines:
        ax.text(0.06, y, "Settings", fontsize=12, fontweight='bold', color='#E65100',
                transform=ax.transAxes, va='top')
        y -= 0.035
        # Wrap each meta line by actual CHARACTER WIDTH (textwrap), same
        # fix and same reason as the "Spectra used" list below: a caller
        # passing a long line (e.g. Melting Curve Analysis's per-
        # component "fraction = ..., midpoint = ..., width = ..." summary
        # line) ran off the right edge of the page uncut before this.
        # Leading whitespace on the original line (used for a couple of
        # callers' own sub-item indentation, e.g. "  Low-T region: ...")
        # is preserved on the first wrapped line and carried into any
        # continuation lines too, so the visual grouping survives
        # wrapping.
        truncated = False
        for line in meta_lines:
            if y < 0.06:
                truncated = True
                break
            stripped = line.lstrip(' ')
            indent = line[:len(line) - len(stripped)]
            wrap_width = max(20, _META_WRAP_CHARS - len(indent))
            wrapped = textwrap.wrap(stripped, width=wrap_width,
                                    break_long_words=False, break_on_hyphens=False) or ['']
            for j, wline in enumerate(wrapped):
                if y < 0.06:
                    truncated = True
                    break
                prefix = indent if j == 0 else indent + '  '
                ax.text(0.08, y, prefix + wline, fontsize=10, transform=ax.transAxes, va='top')
                y -= 0.03
            if truncated:
                break
        if truncated:
            # Same last-resort fallback as the spectra list below --
            # exceptionally long settings blocks stop here rather than
            # running off the bottom of the page uncut.
            ax.text(0.08, max(y, 0.03), "… (see Fit Details / results table for the rest)",
                    fontsize=8, style='italic', color='#888', transform=ax.transAxes, va='top')
            y = max(y, 0.03) - 0.03
        y -= 0.02

    if source_labels:
        ax.text(0.06, y, f"Spectra used ({len(source_labels)})", fontsize=12,
                fontweight='bold', color='#E65100', transform=ax.transAxes, va='top')
        y -= 0.035
        # Wrap by actual CHARACTER WIDTH (textwrap), not by a fixed count
        # of labels per line -- a fixed count overflows the page width as
        # soon as labels are longer than whatever length was assumed (this
        # was the original bug: long "<file> : <spectrum>" labels ran off
        # the right edge of the page uncut). Every label still appears in
        # full; only the line-break positions are chosen to fit.
        joined = ", ".join(source_labels)
        wrapped_lines = textwrap.wrap(joined, width=_LIST_WRAP_CHARS,
                                      break_long_words=False, break_on_hyphens=False)
        for i, line in enumerate(wrapped_lines):
            if y < 0.06:
                # Truncated as a last resort only for pathologically long
                # lists that would run off the bottom of the page even
                # with correct wrapping -- the full list is still
                # recoverable from the results table pages that follow.
                remaining_lines = len(wrapped_lines) - i
                ax.text(0.08, y, f"… ({remaining_lines} more lines, see results table)",
                        fontsize=8, style='italic', color='#888', transform=ax.transAxes, va='top')
                break
            ax.text(0.08, y, line, fontsize=8, transform=ax.transAxes, va='top')
            y -= 0.022

    pdf.savefig(fig)


def _add_existing_figure(pdf, figure):
    """Rasterize an already-built matplotlib Figure (e.g. a dialog's live
    plot) via its own savefig() into an in-memory PNG, then place that
    image onto a freshly-built, consistently-sized landscape page --
    never touches the original Figure's size/layout/style (see module
    docstring for why)."""
    buf = io.BytesIO()
    facecolor = figure.get_facecolor()
    figure.savefig(buf, format='png', dpi=200, facecolor=facecolor)
    buf.seek(0)
    img = mpimg.imread(buf, format='png')

    page = Figure(figsize=_PAGE_SIZE)
    # Axes spans almost the entire page; imshow's default aspect='equal'
    # keeps the image undistorted (letterboxed within the axes as needed)
    # rather than stretching it to fill a mismatched aspect ratio.
    ax = page.add_axes([0.02, 0.02, 0.96, 0.96])
    ax.imshow(img)
    ax.axis('off')
    pdf.savefig(page)


def _add_table_pages(pdf, headers, rows):
    n_cols = len(headers)
    for start in range(0, max(len(rows), 1), _ROWS_PER_PAGE):
        chunk = rows[start:start + _ROWS_PER_PAGE]
        n_rows = len(chunk) if chunk else 1

        # Page height scales with row count (capped at the standard
        # landscape page height) instead of always using a full 8.5in-tall
        # page -- a 2-row table on a full-height page left almost the
        # whole page blank with the table stranded in one corner.
        page_h = min(_PAGE_SIZE[1], max(2.2, 0.9 + 0.32 * (n_rows + 1)))
        fig = Figure(figsize=(_PAGE_SIZE[0], page_h))
        ax = fig.add_axes([0.03, 0.03, 0.94, 0.94])
        ax.axis('off')
        table = ax.table(cellText=chunk if chunk else [[''] * n_cols],
                         colLabels=headers, loc='center', cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        # Deliberately NOT calling table.scale() to enlarge row height:
        # matplotlib's default table sizing already divides the axes'
        # height exactly among however many rows there are, so it can
        # never overflow the page. A vertical scale multiplier here would
        # make rows taller than that exact-fit size and push the table
        # off the top/bottom of the page once row count is high enough
        # to hit the page_h cap above (this was a real bug caught during
        # testing with a 32-row table -- the top and bottom rows were
        # clipped off the page). The page_h formula above already governs
        # how large each row looks, by controlling how few/many rows share
        # a given page height.
        try:
            table.auto_set_column_width(col=list(range(n_cols)))
        except Exception:
            # Column-width auto-sizing is cosmetic only -- a failure here
            # (e.g. an unusual header/value combination) shouldn't block
            # the table from being written at all.
            pass
        pdf.savefig(fig)
