# src/help/help_figures.py
"""Explanatory figures shared by several help pages (how a calculation
works), kept in resources/images/help_screenshots/calculations/ and drawn by
dev_notes/make_calculation_figures.py (a file name with a folder, e.g.
"peak_detection/...", lies in that folder of help_screenshots instead - the
Peak Detection figures, drawn by dev_notes/make_peak_detection_figures.py,
and the Peak Detection windows, by make_tool_screenshots.py). figure_html(key) gives a complete
<div><img><caption></div> block (empty if the file is missing), resolved
with resource_path() so it works from source and in the installed build."""

import os
import struct
from pathlib import Path

from src.modules.utils.resource_path import resource_path

_ROOT = os.path.join("resources", "images", "help_screenshots")
_DIR = os.path.join(_ROOT, "calculations")
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
    'PEAK_LABELS': (
        "peak_detection/labels_threshold_before_now.png",
        "Eleven Raman spectra with their peaks: before, a number on every peak and a band "
        "missed; now every band found and each number written once",
        "Eleven similar Raman spectra (test dataset raman_2comp_clean). Top &ndash; the old "
        "settings: Threshold 0.5 compares a peak with the tallest one, so the clear band at 344 "
        "is missed; every peak gets its number, so they pile up. Bottom &ndash; the defaults now: "
        "Threshold 0 and signal-to-noise 8 judge each peak locally, so all 7 bands are found; "
        "<i>Labels: once per band</i> writes each band's position once, above its highest peak. "
        "The red dots still mark every peak."),
    'PEAK_NOISE': (
        "peak_detection/noisy_cd_signal_to_noise.png",
        "A noisy CD series with and without the signal-to-noise limit",
        "A noisy CD series (cd_2comp_noisy, Peaks: Both). Top &ndash; without a noise limit the "
        "weakest spectra, whose range is not much bigger than their noise, give many peaks that "
        "are only noise (121 dots, 20 numbers). Bottom &ndash; signal-to-noise 8 (the default): "
        "the three real bands. Two of them are written as a range because their extremum moves "
        "through the series."),
    'PEAK_MOVING': (
        "peak_detection/cd_moving_minimum.png",
        "Why the minimum of a CD series moves: it is the sum of overlapping bands",
        "Why a peak position is not always a band position (cd_2comp_clean, whose true bands "
        "are known). Left &ndash; the minimum near 250 nm is the sum of three overlapping "
        "negative bands (241.6 of component 2; 253.5 and 259.8 of component 1); the first "
        "spectrum has its minimum at 247.2, the last at 255.9. Right &ndash; the minimum moves "
        "step by step from 247 to 256 nm as the mixture changes, although no band moves. "
        "Detect Peaks writes it as the range 247.19&ndash;256.18."),
    'PEAK_DIALOG': (
        "peak_detection/detect_peaks_dialog.png",
        "The Peak Detection Settings window",
        "Right-click on the plot &rarr; Detect Peaks: the settings, Apply (the window stays "
        "open), Reset to defaults, Peak list&hellip; and the orange ? (what each setting "
        "means)."),
    'PEAK_BAND_TABLE': (
        "peak_detection/peak_list_band_table.png",
        "The Peak list, tab Band table",
        "Peak list, tab Band table: one row per spectrum, one column per band, here with the "
        "fitted FWHM (Refine by fitting) &mdash; ready to paste into Excel."),
}


def _png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(path)
    return struct.unpack(">II", head[16:24])


def figure_html(key, max_width=_MAX_WIDTH):
    filename, alt, caption = FIGURES[key]
    folder = _ROOT if '/' in filename else _DIR
    path = resource_path(os.path.join(folder, *filename.split('/')))
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
