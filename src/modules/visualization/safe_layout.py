"""fig.tight_layout() that never crashes the window.

Matplotlib's tight_layout() inverts the figure's pixel transform. When the
canvas is 0 pixels wide or high -- squeezed by its layout (e.g. a panel
shown inside another window before it has a size), or a plot collapsed
with a splitter -- that transform cannot be inverted and tight_layout()
raises "numpy.linalg.LinAlgError: Singular matrix". There is nothing to lay
out at that size anyway, so the layout is simply skipped; the next redraw
at a real size lays the figure out again."""
import numpy as np


def safe_tight_layout(fig, **kwargs):
    """Call fig.tight_layout(**kwargs) unless the figure has (almost) no
    size; never raise for a degenerate size. Returns True if the layout
    was applied."""
    try:
        w, h = fig.get_size_inches()
        if w * fig.dpi < 2 or h * fig.dpi < 2:
            return False
        fig.tight_layout(**kwargs)
        return True
    except (np.linalg.LinAlgError, ValueError):
        return False
