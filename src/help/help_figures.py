# src/help/help_figures.py
"""Explanatory figures shared by several help pages (how a calculation
works), kept in resources/images/help_screenshots/calculations/ and drawn by
dev_notes/make_calculation_figures.py. figure_html(key) gives a complete
<div><img><caption></div> block (empty if the file is missing), resolved
with resource_path() so it works from source and in the installed build."""

import os
import struct
from pathlib import Path

from src.modules.utils.resource_path import resource_path

_DIR = os.path.join("resources", "images", "help_screenshots", "calculations")
_MAX_WIDTH = 760

FIGURES = {
    'AREA_OVER_A_RANGE': (
        "area_over_a_range.png",
        "Area over a range: exact range edges, separate parts, ranges not inside a spectrum",
        "How the area over a range is calculated (2D Map, Band Ratio, Group Statistics, "
        "Normalization &ndash; Area). Blue: the area counted; red hatched: what versions "
        "before 1.5 did wrong. 1&nbsp;&ndash; the area runs from exactly the start to exactly "
        "the end of the range (the spectrum is interpolated at the edges). 2&nbsp;&ndash; "
        "several ranges, or the rest after an excluded part, are integrated separately and "
        "added; the gap is not counted. 3&nbsp;&ndash; a spectrum that does not completely "
        "cover the range gets no value (or, in Normalization, is left unchanged) and is "
        "named."),
    'GROUP_VALUES': (
        "group_statistics_values.png",
        "Group Statistics values: point, average or fit at x; highest point or parabola; "
        "range partly outside a spectrum; baseline-corrected area; fitted peak; two bands",
        "What the refined Group Statistics values do. A1 &ndash; Intensity at x: one noisy "
        "point (red) can decide the value; the average over x &plusmn; w (orange) or a small "
        "curve fitted over x &plusmn; w (green) is close to the true value. A2 &ndash; Peak "
        "top: the highest point can be a noise spike; the top of a parabola through the "
        "highest points is not, and lies between measured points. A3 &ndash; a spectrum that "
        "covers only part of the range gets no value (before 1.5: a smaller value from the "
        "part it had). B1 &ndash; baseline-corrected area: the band above the straight line "
        "joining the range edges. B2 &ndash; fitted peak: position, FWHM, height and area of "
        "a peak fitted to the range. C &ndash; ways to combine two bands A and B."),
    'VOIGT_AREA': (
        "voigt_area_tails.png",
        "Voigt peak on a log scale with the far tails that the old area calculation cut off",
        "The area of a Voigt peak (Peak Fitting) is now exact: height divided by the "
        "profile's value at the centre. Before 1.5 it was integrated numerically over "
        "&plusmn;50 widths, which cut off the slowly decaying sides (red hatched) &mdash; up "
        "to 0.6&nbsp;% of the area for Lorentzian-like peaks."),
}


def _png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(path)
    return struct.unpack(">II", head[16:24])


def figure_html(key, max_width=_MAX_WIDTH):
    filename, alt, caption = FIGURES[key]
    path = resource_path(os.path.join(_DIR, filename))
    if not os.path.isfile(path):
        return ''
    try:
        w, h = _png_size(path)
        dw = min(w, max_width)
        dh = round(h * dw / w)
    except (OSError, ValueError):
        dw, dh = max_width, round(max_width * 0.35)
    return (f'<div style="margin:10px 0;"><img src="{Path(path).as_uri()}" width="{dw}" '
            f'height="{dh}" alt="{alt}" style="border:1px solid #dee2e6; border-radius:6px;" />'
            f'<p style="font-size:9pt; color:#555; margin-top:4px;">{caption}</p></div>')


def figure_substitutions():
    """{'AREA_OVER_A_RANGE_FIGURE': html, ...} for string.Template pages."""
    return {f"{key}_FIGURE": figure_html(key) for key in FIGURES}
