# src/help/peak_fitting_help.py

"""
Help content for the Peak Fitting & Deconvolution operation.
"""

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path


# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build. Same mechanism as
# baseline_correction_help.py — see that file for the full rationale.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "peak_fitting")

_SCREENSHOT_FILES = {
    "OVERVIEW":      "dialog_overview.png",
    "PLOT":          "plot_area.png",
    "TABLE":         "peaks_table.png",
    "ADD_CONTROLS":  "peak_adding_controls.png",
    "WIDTH_DIALOG":  "initial_width_dialog.png",
    "FIT_CONTROLS":  "fitting_controls.png",
    "OUTPUT_OPTIONS":"output_options.png",
    "SERIES_OVERVIEW": "series_overview.png",
    "SERIES_RESULTS": "series_results.png",
    "SERIES_BY_SPECTRUM": "series_by_spectrum.png",
    "SERIES_WIDE": "series_wide.png",
    "SERIES_WATERFALL": "series_waterfall.png",
    "SERIES_GRID": "series_grid.png",
    "SPECTRA_LIST": "spectra_list.png",
    "PLOT_BAR": "plot_bar.png",
    "QUICK_HELP": "quick_help.png",
    "MISSING_PEAK": "missing_peak.png",
    "PEAKS_OWN": "peaks_each_own.png",
    "CONSTRAINT_EACH": "constraint_each.png",
    "CONSTRAINT_DROPDOWN": "constraint_dropdown.png",
    "CD_UNRESTRICTED": "cd_fit_unrestricted.png",
    "CD_POSITIVE": "cd_fit_positive.png",
}

# Cap displayed screenshot width at this many pixels — see
# baseline_correction_help.py's _MAX_IMG_WIDTH for the full explanation
# (Qt's rich-text engine doesn't reliably honor CSS max-width on <img>).
_MAX_IMG_WIDTH = 700


def _png_size(path):
    """Return (width, height) in pixels for a PNG, read from its IHDR
    chunk — avoids needing Pillow just to check dimensions."""
    with open(path, "rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a readable PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _resolve_screenshot_uris():
    """Resolve each help screenshot to a file:// URI via resource_path(),
    plus an explicit display width/height (capped at _MAX_IMG_WIDTH,
    aspect ratio preserved) so every <img> tag renders at a sane,
    consistent size instead of at the screenshot's raw captured
    resolution."""
    values = {}
    for key, filename in _SCREENSHOT_FILES.items():
        abs_path = resource_path(os.path.join(_SCREENSHOT_DIR, filename))
        values[key] = Path(abs_path).as_uri()

        try:
            native_w, native_h = _png_size(abs_path)
            display_w = min(native_w, _MAX_IMG_WIDTH)
            display_h = round(native_h * (display_w / native_w))
        except (OSError, ValueError):
            # Screenshot missing/unreadable when the help page is built
            # (e.g. a fresh checkout without the images yet) — fall back
            # to a fixed box instead of crashing the whole help page.
            display_w, display_h = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)

        values[f"{key}_W"] = str(display_w)
        values[f"{key}_H"] = str(display_h)

    return values


def get_peak_fitting_help_title():
    return "Peak Fitting & Deconvolution Help"


def get_peak_fitting_help_content():
    """Return HTML content for comprehensive user guide help."""
    images = _resolve_screenshot_uris()
    from src.help.help_figures import figure_substitutions
    images.update(figure_substitutions())

    # string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which
    # would collide with .format()-style placeholders.
    help_template = Template("""
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { color: #1976D2; margin-top: 1.5em; }
            .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin-top: 10px; }
            .key-feature { background-color: #e3f2fd; padding: 10px; border-left: 4px solid #1e88e5; margin-top: 10px;}
            .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace;}
            li { margin-bottom: 5px; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>
        <h1>Peak Fitting &amp; Deconvolution Help</h1>

        <p><b>Peak Fitting</b> describes the bands of a spectrum by peak shapes (Gaussian,
        Lorentzian, Voigt or Pseudo-Voigt) and adjusts them until their sum matches the data. It
        separates overlapping bands and gives each band its <b>position</b>, <b>height</b>,
        <b>width</b> (FWHM) and <b>area</b> &mdash; for one spectrum, or for many spectra at once
        (a temperature scan, a titration, a time series, or spectra of different kinds).</p>

        <p style="font-size:0.95em;"><b>Contents:</b>
        <a href="#workflow">At a glance</a> &#183;
        <a href="#recommended">Recommended workflow</a> &#183;
        <a href="#window">The window</a> &#183;
        <a href="#adding-peaks">Adding peaks</a> &#183;
        <a href="#peaks-mode">Peaks of several spectra</a> &#183;
        <a href="#fitting">Fitting</a> &#183;
        <a href="#converge">Getting a fit to converge</a> &#183;
        <a href="#viewing">The plot</a> &#183;
        <a href="#series">Fitting a series</a> &#183;
        <a href="#series-results">Series results</a> &#183;
        <a href="#outputs">Output Options</a> &#183;
        <a href="#models">Peak shapes</a> &#183;
        <a href="#details">Details</a></p>

        <h2 id="workflow">How it works &mdash; at a glance</h2>
        <svg viewBox="0 0 960 545" xmlns="http://www.w3.org/2000/svg" style="width:100%; max-width:860px; height:auto; display:block; margin:8px auto; font-family:Arial,sans-serif;">
            <defs>
                <marker id="pfA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#78909C"/>
                </marker>
                <marker id="pfR" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#C62828"/>
                </marker>
                <filter id="pfShadow" x="-10%" y="-10%" width="120%" height="130%">
                    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.18"/>
                </filter>
            </defs>

            <!-- ===== row 1: 1 → 2 → 3 → 4 ===== -->
            <!-- card 1: select -->
            <g filter="url(#pfShadow)">
                <rect x="10" y="10" width="210" height="160" rx="10" fill="#fff" stroke="#2E7D32"/>
                <path d="M 10 20 a 10 10 0 0 1 10 -10 h 190 a 10 10 0 0 1 10 10 v 22 h -210 z" fill="#2E7D32"/>
            </g>
            <text x="115" y="33" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">1 &#183; Select spectra</text>
            <rect x="40" y="56" width="150" height="14" rx="3" fill="#ECEFF1"/>
            <rect x="40" y="74" width="150" height="14" rx="3" fill="#4A7FC1"/>
            <rect x="40" y="92" width="150" height="14" rx="3" fill="#4A7FC1"/>
            <rect x="40" y="110" width="150" height="14" rx="3" fill="#ECEFF1"/>
            <text x="115" y="152" font-size="12" fill="#37474F" text-anchor="middle">main window &#8250; Peak Fitting</text>

            <line x1="222" y1="90" x2="246" y2="90" stroke="#78909C" stroke-width="2.5" marker-end="url(#pfA)"/>

            <!-- card 2: peaks -->
            <g filter="url(#pfShadow)">
                <rect x="250" y="10" width="210" height="160" rx="10" fill="#fff" stroke="#1976D2"/>
                <path d="M 250 20 a 10 10 0 0 1 10 -10 h 190 a 10 10 0 0 1 10 10 v 22 h -210 z" fill="#1976D2"/>
            </g>
            <text x="355" y="33" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">2 &#183; Peaks</text>
            <line x1="270" y1="128" x2="440" y2="128" stroke="#B0BEC5"/>
            <path d="M 270 127 C 300 127, 305 70, 320 70 C 335 70, 338 127, 352 120 C 365 112, 370 95, 385 95 C 400 95, 405 127, 440 127" fill="none" stroke="#757575" stroke-width="2"/>
            <path d="M 290 128 C 305 128, 310 72, 320 72 C 330 72, 335 128, 350 128" fill="#1976D2" fill-opacity="0.18" stroke="#1976D2" stroke-dasharray="4,3"/>
            <path d="M 362 128 C 372 128, 378 97, 385 97 C 392 97, 398 128, 410 128" fill="#F57C00" fill-opacity="0.18" stroke="#F57C00" stroke-dasharray="4,3"/>
            <text x="355" y="152" font-size="12" fill="#37474F" text-anchor="middle">Auto-Detect &#183; click &#183; Copy/Paste</text>

            <line x1="462" y1="90" x2="486" y2="90" stroke="#78909C" stroke-width="2.5" marker-end="url(#pfA)"/>

            <!-- card 3: constraint -->
            <g filter="url(#pfShadow)">
                <rect x="490" y="10" width="210" height="160" rx="10" fill="#fff" stroke="#1976D2"/>
                <path d="M 490 20 a 10 10 0 0 1 10 -10 h 190 a 10 10 0 0 1 10 10 v 22 h -210 z" fill="#1976D2"/>
            </g>
            <text x="595" y="33" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">3 &#183; Constraint</text>
            <line x1="510" y1="100" x2="680" y2="100" stroke="#B0BEC5"/>
            <path d="M 515 100 C 535 100, 540 60, 552 60 C 564 60, 569 100, 589 100" fill="none" stroke="#2E7D32" stroke-width="2.5"/>
            <text x="552" y="54" font-size="15" fill="#2E7D32" text-anchor="middle" font-weight="bold">+</text>
            <path d="M 601 100 C 621 100, 626 136, 638 136 C 650 136, 655 100, 675 100" fill="none" stroke="#C62828" stroke-width="2.5"/>
            <text x="638" y="125" font-size="15" fill="#C62828" text-anchor="middle" font-weight="bold">&#8722;</text>
            <text x="595" y="158" font-size="12" fill="#37474F" text-anchor="middle">one for all, or each its own</text>

            <line x1="702" y1="90" x2="726" y2="90" stroke="#78909C" stroke-width="2.5" marker-end="url(#pfA)"/>

            <!-- card 4: fit -->
            <g filter="url(#pfShadow)">
                <rect x="730" y="10" width="220" height="160" rx="10" fill="#fff" stroke="#F57C00"/>
                <path d="M 730 20 a 10 10 0 0 1 10 -10 h 200 a 10 10 0 0 1 10 10 v 22 h -220 z" fill="#F57C00"/>
            </g>
            <text x="840" y="33" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">4 &#183; Fit Peaks</text>
            <rect x="760" y="66" width="160" height="40" rx="8" fill="#FFF3E0" stroke="#F57C00"/>
            <path d="M 778 76 L 778 96 L 795 86 z" fill="#2E7D32"/>
            <text x="805" y="91" font-size="13" fill="#E65100" font-weight="bold">Fit Peaks &#8211; N</text>
            <text x="840" y="132" font-size="12" fill="#37474F" text-anchor="middle">the spectra selected</text>
            <text x="840" y="148" font-size="12" fill="#37474F" text-anchor="middle">in the list</text>

            <!-- turn down to row 2 -->
            <path d="M 840 172 L 840 196 L 820 196" fill="none" stroke="#78909C" stroke-width="2.5"/>
            <line x1="820" y1="196" x2="700" y2="196" stroke="#78909C" stroke-width="2.5"/>
            <line x1="700" y1="196" x2="700" y2="216" stroke="#78909C" stroke-width="2.5" marker-end="url(#pfA)"/>

            <!-- ===== row 2: 5 → 6 → 7 (right to left reads as a U) ===== -->
            <!-- card 5: check -->
            <g filter="url(#pfShadow)">
                <rect x="590" y="220" width="220" height="160" rx="10" fill="#fff" stroke="#6A1B9A"/>
                <path d="M 590 230 a 10 10 0 0 1 10 -10 h 200 a 10 10 0 0 1 10 10 v 22 h -220 z" fill="#6A1B9A"/>
            </g>
            <text x="700" y="243" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">5 &#183; Check the fit</text>
            <line x1="610" y1="292" x2="790" y2="292" stroke="#6A1B9A" stroke-dasharray="3,3"/>
            <path d="M 610 292 l 6 -5 l 6 9 l 6 -7 l 6 4 l 6 -6 l 6 8 l 6 -3 l 6 2 l 6 -7 l 6 9 l 6 -4 l 6 3 l 6 -6 l 6 5 l 6 -2 l 6 4 l 6 -8 l 6 6 l 6 -2 l 6 3 l 6 -5 l 6 7 l 6 -4 l 6 2 l 6 -3 l 6 5 l 6 -4 l 6 3 l 6 -1" fill="none" stroke="#8E24AA" stroke-width="1.5"/>
            <text x="700" y="328" font-size="12" fill="#37474F" text-anchor="middle">residual: noise around zero</text>
            <text x="700" y="352" font-size="14" text-anchor="middle"><tspan fill="#2E7D32">&#10003; good</tspan>  <tspan fill="#F57C00">&#9888; poor</tspan>  <tspan fill="#C62828">&#10007; failed</tspan></text>

            <!-- poor fit: back to the peaks -->
            <path d="M 630 218 C 600 190, 440 205, 400 174" fill="none" stroke="#C62828" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#pfR)"/>
            <text x="330" y="196" font-size="12" fill="#C62828" text-anchor="end" font-style="italic">poor fit: correct the peaks, fit again</text>

            <line x1="588" y1="300" x2="564" y2="300" stroke="#78909C" stroke-width="2.5" marker-end="url(#pfA)"/>

            <!-- card 6: series results -->
            <g filter="url(#pfShadow)">
                <rect x="340" y="220" width="220" height="160" rx="10" fill="#fff" stroke="#00838F"/>
                <path d="M 340 230 a 10 10 0 0 1 10 -10 h 200 a 10 10 0 0 1 10 10 v 22 h -220 z" fill="#00838F"/>
            </g>
            <text x="450" y="243" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">6 &#183; Series results</text>
            <rect x="370" y="264" width="160" height="72" fill="#E0F7FA" stroke="#80DEEA"/>
            <rect x="370" y="264" width="160" height="14" fill="#00838F"/>
            <line x1="370" y1="296" x2="530" y2="296" stroke="#80DEEA"/>
            <line x1="370" y1="314" x2="530" y2="314" stroke="#80DEEA"/>
            <line x1="420" y1="264" x2="420" y2="336" stroke="#80DEEA"/>
            <line x1="475" y1="264" x2="475" y2="336" stroke="#80DEEA"/>
            <text x="450" y="358" font-size="12" fill="#37474F" text-anchor="middle">Copy &#183; Export &#183; Data table</text>

            <line x1="338" y1="300" x2="314" y2="300" stroke="#78909C" stroke-width="2.5" marker-end="url(#pfA)"/>

            <!-- card 7: OK -->
            <g filter="url(#pfShadow)">
                <rect x="90" y="220" width="220" height="160" rx="10" fill="#fff" stroke="#455A64"/>
                <path d="M 90 230 a 10 10 0 0 1 10 -10 h 200 a 10 10 0 0 1 10 10 v 22 h -220 z" fill="#455A64"/>
            </g>
            <text x="200" y="243" font-size="14" fill="#fff" text-anchor="middle" font-weight="bold">7 &#183; OK</text>
            <path d="M 112 300 C 130 300, 135 268, 145 268 C 155 268, 160 300, 178 300" fill="none" stroke="#D32F2F" stroke-width="2"/>
            <path d="M 190 300 l 5 -4 l 5 6 l 5 -5 l 5 3 l 5 -4 l 5 5 l 5 -2 l 5 3" fill="none" stroke="#8E24AA" stroke-width="1.5"/>
            <path d="M 240 300 C 252 300, 256 280, 262 280 C 268 280, 272 300, 288 300" fill="none" stroke="#1976D2" stroke-width="2" stroke-dasharray="4,3"/>
            <text x="145" y="320" font-size="11" fill="#555" text-anchor="middle">fit</text>
            <text x="215" y="320" font-size="11" fill="#555" text-anchor="middle">residual</text>
            <text x="264" y="320" font-size="11" fill="#555" text-anchor="middle">peaks</text>
            <text x="200" y="352" font-size="12" fill="#37474F" text-anchor="middle">Output Options &#8594; new spectra</text>

            <!-- ===== several spectra: three cases ===== -->
            <text x="10" y="418" font-size="14" fill="#E65100" font-weight="bold">Several spectra &#8211; three typical cases:</text>
            <rect x="10" y="430" width="300" height="104" rx="10" fill="#FFF8E1" stroke="#FFB300"/>
            <text x="24" y="454" font-size="13" fill="#E65100" font-weight="bold">A band moves along a series</text>
            <text x="24" y="476" font-size="12" fill="#37474F">&#8226; peaks on the first spectrum only</text>
            <text x="24" y="495" font-size="12" fill="#37474F">&#8226; tick &#8220;start from the fit before them&#8221;</text>
            <text x="24" y="514" font-size="12" fill="#37474F">&#8226; All &#8594; Fit Peaks</text>
            <rect x="330" y="430" width="300" height="104" rx="10" fill="#FFF8E1" stroke="#FFB300"/>
            <text x="344" y="454" font-size="13" fill="#E65100" font-weight="bold">The same peaks for all</text>
            <text x="344" y="476" font-size="12" fill="#37474F">&#8226; fit one spectrum, Copy peaks</text>
            <text x="344" y="495" font-size="12" fill="#37474F">&#8226; All &#8594; Paste peaks &#8594; Fit Peaks</text>
            <text x="344" y="514" font-size="12" fill="#6D4C41">&#8226; on several cores: fast</text>
            <rect x="650" y="430" width="300" height="104" rx="10" fill="#FFF8E1" stroke="#FFB300"/>
            <text x="664" y="454" font-size="13" fill="#E65100" font-weight="bold">Different spectra (e.g. Raman + CD)</text>
            <text x="664" y="476" font-size="12" fill="#37474F">&#8226; All &#8594; Auto-Detect Peaks &#8211; N spectra</text>
            <text x="664" y="495" font-size="12" fill="#37474F">&#8226; constraint: Each spectrum its own</text>
            <text x="664" y="514" font-size="12" fill="#37474F">&#8226; All &#8594; Fit Peaks</text>
        </svg>

        <h2 id="recommended">Recommended workflow</h2>
        <p><b>Before you start:</b> correct the baseline (Baseline Correction) and, if needed, cut
        the spectra to the region of interest (Define Spectral Range). The fit always uses the
        whole spectrum shown, and the peaks have no baseline of their own.</p>
        <h3>One spectrum</h3>
        <ol>
            <li>Click <b>Auto-Detect Peaks</b>, then check the table: remove peaks you do not want,
            add missing ones by clicking on the top of a band in the plot
            (<a href="#adding-peaks">Adding peaks</a>).</li>
            <li>Choose the <b>Amplitude Constraint</b> &mdash; <b>Positive Peaks Only</b> for
            spectra that only go up (Raman, IR absorbance, fluorescence).</li>
            <li>Click <b>Fit Peaks</b>. The residual should look like noise around zero; if the fit
            is poor, see <a href="#converge">Getting a fit to converge</a>.</li>
            <li>Tick the <b>Output Options</b> you want to keep as new spectra and click <b>OK</b>
            (<a href="#ok-behavior">what OK does</a>). <b>Copy Results</b> copies the numbers for
            Excel.</li>
        </ol>
        <h3>Several spectra</h3>
        <ol>
            <li>Select all of them in the main window, then open Peak Fitting: a list of the
            spectra appears beside the plot.</li>
            <li>Set up and fit the peaks on one spectrum, as above.</li>
            <li>Give the other spectra their peaks in one of the three ways of the scheme above
            (Auto-Detect for each, Copy/Paste, or start from the fit before them).</li>
            <li><b>Select the spectra to fit</b> in the list (<b>All</b> for the whole series) and
            click <b>Fit Peaks &ndash; N selected spectra</b>.</li>
            <li>Look through the results: the tab <b>Series results</b> (By peak, By spectrum or
            All in one table),
            the marks &#10003; / &#9888; / &#10007; in the list, several spectra together in
            Overlay, Waterfall or Grid. Correct a poor fit on its own.</li>
            <li>Copy or export the table, open it in the Data table, or click OK with Output
            Options.</li>
        </ol>

        <h2 id="window">The window</h2>
        <div class="screenshot">
            <img src="$OVERVIEW" width="${OVERVIEW_W}" height="${OVERVIEW_H}" alt="Peak Fitting window: the peaks table and controls on the left, the list of spectra in the middle, the plot with the fit and residual on the right" />
            <p class="caption">The Peak Fitting window with a series of ten Raman spectra (raman_2comp_noisy).</p>
        </div>
        <ul>
            <li><b>Left</b> &mdash; the tab <b>Peaks</b> (the peaks of the shown spectrum and the
            buttons to add, copy, remove them) and the tab <b>Series results</b>; below them
            <b>Fitting</b> (Amplitude Constraint, Fit Peaks) and <b>Output Options</b>.</li>
            <li><b>Middle</b> (with several spectra) &mdash; the list of the spectra: select one to
            see it alone, several to see them together; <b>All</b> and <b>Fitted</b> select
            quickly.</li>
            <li><b>Right</b> &mdash; the plot: the shown spectrum with its fit and the residual, or
            several spectra together.</li>
        </ul>
        <p>The small orange <b>?</b> buttons give a short help on each part of the window, with a
        link to its section here.</p>
        <div class="screenshot">
            <img src="$QUICK_HELP" width="${QUICK_HELP_W}" height="${QUICK_HELP_H}" alt="The short help of the orange question mark next to the Amplitude Constraint" />
            <p class="caption">The orange "?" next to the Amplitude Constraint: what helps a fit; Full help&hellip; opens the section here.</p>
        </div>

        <h2 id="adding-peaks">Adding peaks</h2>
        <p>The table <b>Peaks to Fit</b> holds the starting values of the fit: one row per peak with
        its shape (Model), Center, Height and Width. The fit starts from these values,
        so they should describe the bands roughly. The starting peaks are drawn as dashed lines.</p>
        <ul>
            <li><b>Auto-Detect Peaks</b> finds the bands of the shown spectrum: every maximum that
            stands out by at least 10&nbsp;% of the spectrum's range and clearly above the noise
            (looked for in lightly smoothed data, so a single noisy point is not taken for a
            narrow peak).
            Each gets its position, height and width (&sigma;, from the band's width at half
            height). Negative bands are found only where the data really go below the baseline
            &mdash; the dip between two neighbouring bands is not a peak. Peaks already in the
            table are not added again.</li>
            <li><b>Add via Click</b> (ticked by default): click on the top of a band in the plot.
            A Gaussian peak is added there, with the width of the band under the click (its width
            at half height). Where no band can be measured (a shoulder, flat baseline) it gets the
            initial width: right-click <b>Auto-Detect Peaks</b> &rsaquo; <b>Set Initial Peak
            Width&hellip;</b>. A width set there is used for every clicked peak.</li>
            <li><b>Zoom and Pan</b> (the plot's toolbar): choosing Zoom or Pan switches Add via
            Click off, so dragging does not add peaks; tick Add via Click again to add more. The
            line next to the toolbar tells which of the two a click on the plot does. Home (the
            house) shows the whole spectrum again.</li>
            <li><b>Edit</b> any value: double-click a cell. Double-click the colour swatch to change
            the colour. <b>Extra</b> is the 4th value of Voigt (&gamma;) and Pseudo-Voigt (&eta;);
            Gaussian and Lorentzian have none ("&mdash;").</li>
            <li><b>Which peak is which</b>: select a row (or several) in the table &mdash; that
            peak is drawn thick and filled in the plot.</li>
            <li><b>Remove</b>: select rows and press Delete, or <b>Remove Selected Peak(s)</b>;
            <b>Clear All Peaks</b> empties the table.</li>
        </ul>

        <h3 id="peaks-mode">Several spectra: each has its own peaks</h3>
        <p>With several spectra, <b>every spectrum has its own peaks</b>, and everything acts
        <b>only on the spectra selected in the list</b> beside the plot &mdash; spectra that are
        not selected are never changed:</p>
        <ul>
            <li>The table shows the peaks of the <b>shown spectrum</b> (its name is in the title,
            e.g. <i>Peaks of uv_03 (the shown spectrum)</i>). Adding a peak by clicking on the
            plot (Add via Click), changing a value in the table, <b>Remove Selected Peak(s)</b>
            change only the peaks of this spectrum. Its fit then no longer belongs to these
            peaks: Series results shows it as not fitted yet until you click Fit Peaks again.</li>
            <li><b>Clear All Peaks</b> clears the shown spectrum; with several selected,
            <b>Clear All Peaks &ndash; N spectra</b> clears all of them (and their fits).</li>
            <li>The shown spectrum changes only when you select <b>one</b> spectrum alone (a plain
            click, or &#9664; &#9654;). Adding spectra to the selection (Ctrl+click, Shift+click,
            All) keeps it.</li>
            <li><b>Auto-Detect Peaks</b> finds the peaks of the shown spectrum; with several
            selected, <b>Auto-Detect Peaks &ndash; N spectra</b> finds the peaks of each of them,
            each into its own list.</li>
            <li><b>Copy peaks of &hellip;</b> remembers the peaks of the shown spectrum;
            <b>Paste peaks of &hellip; to the selected spectra (N)</b> gives them to the spectra
            selected in the list (replacing theirs) &mdash; for a series of similar spectra: set
            up the peaks on one, Copy, select the others (All), Paste, then fit.</li>
            <li><b>Fit Peaks &ndash; N selected spectra</b> fits the selected spectra, each from
            <b>its own peaks</b>; spectra without peaks are left out &mdash; unless <b>Spectra
            without peaks: start from the fit before them</b> is ticked (see
            <a href="#series">Fitting a series</a>).</li>
            <li>In the list, spectra with peaks have a <b>green dot</b> and green bold names (the dot
            is seen also when they are selected); those without peaks are grey.</li>
        </ul>
        <p>So for spectra with different bands (e.g. Raman and CD spectra selected together):
        select all, Auto-Detect Peaks &ndash; N spectra, Fit Peaks &ndash; each is fitted from its
        own peaks. In Series results, Peak 1, Peak 2, &hellip; are each spectrum's own peaks in
        the order of its table (All in one table has as many peak columns as the spectrum with
        the most peaks).</p>
        <div class="screenshot">
            <img src="$PEAKS_OWN" width="${PEAKS_OWN_W}" height="${PEAKS_OWN_H}" alt="Raman and CD spectra together, each fitted with its own peaks, shown in Grid" />
            <p class="caption">Five Raman and five CD spectra selected together: Auto-Detect Peaks &ndash; 10 spectra found each one's own peaks (the CD ones a band up and a band down), and each was fitted from them with its own constraint (Grid).</p>
        </div>
        <div class="screenshot">
            <img src="$TABLE" width="${TABLE_W}" height="${TABLE_H}" alt="Peaks to Fit table with Color, Model, Center, Height, Width, and Extra columns" />
            <p class="caption">The Peaks to Fit table.</p>
        </div>
        <div class="screenshot">
            <img src="$ADD_CONTROLS" width="${ADD_CONTROLS_W}" height="${ADD_CONTROLS_H}" alt="Auto-Detect Peaks, Add via Click, Remove Selected Peak(s) and Clear All Peaks" />
            <p class="caption">Adding and removing peaks.</p>
        </div>
        <div class="screenshot">
            <img src="$WIDTH_DIALOG" width="${WIDTH_DIALOG_W}" height="${WIDTH_DIALOG_H}" alt="Set Initial Peak Width dialog, opened by right-clicking Auto-Detect Peaks" />
            <p class="caption">Set Initial Peak Width&hellip; (right-click Auto-Detect Peaks).</p>
        </div>

        <h2 id="fitting">Fitting</h2>
        <ul>
            <li><b>Amplitude Constraint</b>: <i>Unrestricted</i> (peaks may be positive or
            negative), <i>Positive Peaks Only</i>, or <i>Negative Peaks Only</i>.
            <div class="screenshot">
                <img src="$CONSTRAINT_DROPDOWN" width="${CONSTRAINT_DROPDOWN_W}" height="${CONSTRAINT_DROPDOWN_H}" alt="The Amplitude Constraint drop-down open: Unrestricted, Positive Peaks Only, Negative Peaks Only" />
                <p class="caption">The Amplitude Constraint: Unrestricted, Positive Peaks Only, Negative Peaks Only.</p>
            </div>
            Normally one constraint for all spectra. With several spectra of different kinds tick <b>Each
            spectrum its own</b>: the constraint chosen then applies to the spectra selected in
            the list &mdash; e.g. select the Raman spectra and choose Positive Peaks Only, then
            select the CD spectra and choose Unrestricted. The list marks Positive with (+) and
            Negative with (&minus;); when the selected spectra have different constraints the
            drop-down shows <i>&mdash; mixed &mdash;</i> and a line under it says how many have
            which (choosing one sets it for all of them). Unticked again, the one constraint for
            all applies (the own ones are kept for next time).
            <p>Why it matters &mdash; a CD spectrum has bands pointing up <i>and</i> down:</p>
            <div class="screenshot">
                <img src="$CD_UNRESTRICTED" width="${CD_UNRESTRICTED_W}" height="${CD_UNRESTRICTED_H}" alt="A CD spectrum fitted with Unrestricted: one band up, one band down, a good fit" />
                <p class="caption">A CD spectrum with <b>Unrestricted</b>: the band up and the band down are both fitted.</p>
            </div>
            <div class="screenshot">
                <img src="$CD_POSITIVE" width="${CD_POSITIVE_W}" height="${CD_POSITIVE_H}" alt="The same CD spectrum fitted with Positive Peaks Only: the band down cannot be fitted, a large residual" />
                <p class="caption">The same spectrum with <b>Positive Peaks Only</b>: the band down cannot be described &mdash; it stays in the residual (and the fit is marked &#9888;).</p>
            </div>
            <div class="screenshot">
                <img src="$CONSTRAINT_EACH" width="${CONSTRAINT_EACH_W}" height="${CONSTRAINT_EACH_H}" alt="Each spectrum its own constraint: the Raman spectra Positive Peaks Only (+), the CD spectra Unrestricted; all selected: mixed" />
                <p class="caption">Each spectrum its own constraint: the Raman spectra Positive Peaks Only (+), the CD spectra Unrestricted; with all selected the drop-down shows &mdash; mixed &mdash;.</p>
            </div></li>
            <li><b>Fit Peaks</b> adjusts all peaks of the table together. With one spectrum it fits
            that one; with a series it fits the spectra <b>selected in the list</b> beside the plot
            &mdash; its text says how many (<i>Fit Peaks &ndash; 1 spectrum</i>, <i>Fit Peaks
            &ndash; 10 selected spectra</i>). The table then shows the fitted values of the shown
            spectrum, the plot the total fit (red), each peak (dotted) and the residual.</li>
            <li>Without peaks in the table, Fit Peaks is greyed out and a line under it says what
            to do first (Auto-Detect Peaks, or Add via Click).</li>
            <li>The button next to Fit Peaks copies for Excel, and its name says what. On the tab
            <b>Peaks</b>: <b>Copy table &ndash; raman_12</b> copies the peaks table of the shown
            spectrum (with FWHM and area): its start values, or after Fit Peaks its fitted values.
            On the tab <b>Series results</b> it copies what is shown there (By peak, By spectrum or
            All in one table) for the spectra selected in the list &mdash; those in the plot: e.g.
            <b>Copy peak 1 &ndash; 2 spectra</b> or <b>Copy results &ndash; 2 spectra</b> (a spectrum
            not fitted yet gives an empty row). With one spectrum it is called <b>Copy
            Results</b>.</li>
        </ul>
        <p>The fit is kept within the data: no peak higher than three times the largest value of
        the spectrum, no centre outside the spectrum, no width beyond half of its x range. Each
        centre may move by at most two widths from its starting value.</p>
        <div class="screenshot">
            <img src="$FIT_CONTROLS" width="${FIT_CONTROLS_W}" height="${FIT_CONTROLS_H}" alt="Amplitude Constraint, Fit Peaks for 10 selected spectra and Copy results" />
            <p class="caption">Fitting with all ten spectra selected: the one Fit Peaks button says how many it fits; the line under it which spectra have no peaks of their own.</p>
        </div>

        <h3 id="converge">Getting a fit to converge</h3>
        <p>A fit "fails" (the message <i>The fitting algorithm could not converge</i>) or gives
        nonsense &mdash; e.g. two huge peaks, one positive and one negative, cancelling each other
        &mdash; when the starting peaks do not describe the bands well enough. What helps most:</p>
        <ol>
            <li><b>Use the right constraint.</b> For spectra that only go up (Raman, IR absorbance,
            fluorescence) choose <b>Positive Peaks Only</b>. With Unrestricted the fit is free to
            use large positive and negative peaks that cancel out.</li>
            <li><b>One peak per band.</b> Remove peaks lying on flat baseline, peaks much broader
            than the bands around them, and the second of two peaks at almost the same position.
            Every extra peak makes the fit slower and less stable.</li>
            <li><b>Add a peak where a band is missing.</b> A wave left in the residual at one place
            means a band there is not described: click on it to add a peak, then fit again.
            <div class="screenshot">
                <img src="$MISSING_PEAK" width="${MISSING_PEAK_W}" height="${MISSING_PEAK_H}" alt="A fit without a peak for the band at 1293: the residual shows a peak there" />
                <p class="caption">The band at about 1293 has no peak in the table: the fit leaves it out and the residual shows it clearly.</p>
            </div></li>
            <li><b>Starting widths close to the bands.</b> Auto-Detect and Add via Click measure
            them; a typed width is in &sigma; for Gaussian (FWHM &divide; 2.355).</li>
            <li><b>Correct the baseline first.</b> The peaks have no baseline term: a sloping or
            raised baseline is otherwise "explained" by very broad peaks.</li>
            <li><b>Fit a part.</b> For a long spectrum with many bands, cut it to the region of
            interest first (Define Spectral Range) &mdash; fewer peaks fit faster and better.</li>
            <li><b>Start from a good fit.</b> After a successful fit the table holds the fitted
            values; adjust one peak and fit again rather than starting from scratch.</li>
            <li><b>Simpler shapes first.</b> Fit with Gaussians, then change the model of the
            peaks to Voigt or Pseudo-Voigt and fit again from that result.</li>
        </ol>
        <p>A good fit has a residual that looks like noise around zero, and an R&sup2; (in Series
        results) close to 1.</p>

        <h2 id="viewing">The plot</h2>
        <ul>
            <li><b>Grey points</b> &mdash; the data; <b>dashed lines</b> &mdash; the starting
            peaks; <b>red line</b> &mdash; the total fit (sum of the peaks); <b>dotted lines</b>
            &mdash; each fitted peak.</li>
            <li><b>Residual</b> (the plot below) &mdash; data minus fit. It should be small noise
            around zero.</li>
            <li>The check boxes <b>Residual</b> and <b>Legend</b> above the plot hide the residual
            plot and the legend (e.g. when many peaks make the legend cover the spectrum). Both are
            shown by default and the window remembers your choice. Residual applies to one
            spectrum; Legend also to Overlay and Waterfall; in Grid each small plot has the
            spectrum's name as its title.</li>
        </ul>
        <div class="screenshot">
            <img src="$PLOT" width="${PLOT_W}" height="${PLOT_H}" alt="The plot: grey data, red total fit, dotted single peaks and the residual below" />
            <p class="caption">Data (grey), total fit (red), single peaks (dotted) and the residual.</p>
        </div>
        <div class="screenshot">
            <img src="$PLOT_BAR" width="${PLOT_BAR_W}" height="${PLOT_BAR_H}" alt="The row above the plot: Spectra, previous and next arrows, the shown spectrum, Several selected, Residual, Legend and the toolbar with the hint" />
            <p class="caption">Above the plot: the list on/off (Spectra), &#9664; &#9654;, the shown spectrum, how several are shown, Residual, Legend; below them the toolbar and what a click on the plot does.</p>
        </div>
        <p>With several spectra, a <b>list of the spectra</b> is beside the plot and works as in
        the main window:</p>
        <ul>
            <li><b>One spectrum selected</b> &mdash; it alone, with its fit, single peaks and
            residual. Peaks are added by clicking only in this view. &#9664; &#9654; above the plot
            go to the previous or next spectrum; its name is shown next to them. The tab Peaks
            lists the peaks of this spectrum.</li>
            <li><b>Several selected</b> (Ctrl+click, Shift+click, or <b>All</b> / <b>Fitted</b>
            under the list) &mdash; shown together, as chosen in <b>Several selected</b>:
            <b>Overlay</b> (in one plot), <b>Waterfall</b> (each shifted up a little) or
            <b>Grid</b> (one small plot each, at most 16). Each spectrum has its own colour: the
            data thin, its fit thick. Before fitting only the data are drawn.</li>
            <li>In the list, spectra with peaks to fit have a <b>green dot</b> (green bold names),
            those without peaks are grey; fitted spectra are marked &#10003;, a poor fit
            (R&sup2; below 0.9) &#9888; and a failed fit &#10007;. A long name is
            shortened next to &#9664; &#9654; (the whole name in its tooltip). The button
            <b>Spectra</b> hides or shows the list.</li>
        </ul>
        <div class="screenshot">
            <img src="$SPECTRA_LIST" width="${SPECTRA_LIST_W}" height="${SPECTRA_LIST_H}" alt="The list of spectra beside the plot, three of them selected, all fitted" />
            <p class="caption">The list of spectra: three selected, all fitted (&#10003;); All and Fitted below.</p>
        </div>
        <div class="screenshot">
            <img src="$SERIES_WATERFALL" width="${SERIES_WATERFALL_W}" height="${SERIES_WATERFALL_H}" alt="Waterfall: ten fitted spectra, each shifted up" />
            <p class="caption">Several selected &rsaquo; Waterfall: each spectrum shifted up a little, data thin, its fit thick.</p>
        </div>
        <div class="screenshot">
            <img src="$SERIES_GRID" width="${SERIES_GRID_W}" height="${SERIES_GRID_H}" alt="Grid: one small plot per spectrum with its R squared" />
            <p class="caption">Several selected &rsaquo; Grid: one small plot per spectrum, its R&sup2; in the title.</p>
        </div>

        <h2 id="series">Fitting a series</h2>
        <p>To follow the same bands through a whole series (e.g. a temperature scan), select all
        its spectra in the main window before opening Peak Fitting. The list beside the plot
        shows them; a <span style="color:#2E7D32;">green dot</span> marks a spectrum that has
        peaks, &#10003; one that is fitted.</p>
        <p><b>The rule: every selected spectrum needs a start.</b> That is either <b>its own
        peaks</b> (green dot), or &mdash; with <i>Spectra without peaks: start from the fit before
        them</i> ticked &mdash; the fit of a <b>selected</b> spectrum before it in the list.
        <b>Fit Peaks &ndash; N selected spectra</b> is greyed while none of the selected spectra
        has a start, and the orange line under it says what to do. Three ways to give them a
        start:</p>
        <svg viewBox="0 0 960 590" xmlns="http://www.w3.org/2000/svg" style="width:100%; max-width:860px; height:auto; display:block; margin:8px auto; font-family:Arial,sans-serif;">
            <defs>
                <marker id="srA" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#546E7A"/>
                </marker>
                <filter id="srShadow" x="-10%" y="-10%" width="120%" height="130%">
                    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity="0.18"/>
                </filter>
            </defs>
            <!-- card A: the same peaks for all -->
            <g filter="url(#srShadow)">
                <rect x="10" y="10" width="300" height="330" rx="10" fill="#fff" stroke="#2E7D32"/>
                <path d="M 10 20 a 10 10 0 0 1 10 -10 h 280 a 10 10 0 0 1 10 10 v 24 h -300 z" fill="#2E7D32"/>
            </g>
            <text x="160" y="34" font-size="15" fill="#fff" text-anchor="middle" font-weight="bold">A &#183; The same peaks for all</text>
            <g font-size="12" fill="#fff">
                <rect x="30" y="62" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="56" y="76">spectrum 1</text><circle cx="42" cy="72" r="5" fill="#66BB6A" stroke="#fff"/>
                <rect x="30" y="86" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="56" y="100">spectrum 2</text>
                <rect x="30" y="110" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="56" y="124">spectrum 3</text>
                <rect x="30" y="134" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="56" y="148">spectrum 4</text>
            </g>
            <rect x="210" y="62" width="80" height="44" rx="6" fill="#E8F5E9" stroke="#2E7D32"/>
            <text x="250" y="80" font-size="12" fill="#1B5E20" text-anchor="middle">Copy</text>
            <text x="250" y="96" font-size="12" fill="#1B5E20" text-anchor="middle">peaks</text>
            <line x1="162" y1="72" x2="206" y2="76" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <path d="M 250 108 C 250 140, 200 150, 166 100" fill="none" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <path d="M 250 108 C 250 150, 205 160, 166 124" fill="none" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <path d="M 250 108 C 250 160, 210 170, 166 148" fill="none" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <text x="262" y="150" font-size="12" fill="#1B5E20">Paste</text>
            <text x="30" y="200" font-size="12.5" fill="#37474F">1. select spectrum 1 alone, set its</text>
            <text x="30" y="217" font-size="12.5" fill="#37474F">    peaks, Fit Peaks, Copy peaks</text>
            <text x="30" y="240" font-size="12.5" fill="#37474F">2. select the others (or All)</text>
            <text x="30" y="263" font-size="12.5" fill="#37474F">3. Paste peaks to the selected spectra</text>
            <text x="30" y="286" font-size="12.5" fill="#37474F">4. Fit Peaks &#8211; N selected spectra</text>
            <text x="30" y="320" font-size="12" fill="#607D8B" font-style="italic">all from the same start, fast</text>
            <!-- card B: a band that moves -->
            <g filter="url(#srShadow)">
                <rect x="330" y="10" width="300" height="330" rx="10" fill="#fff" stroke="#1976D2"/>
                <path d="M 330 20 a 10 10 0 0 1 10 -10 h 280 a 10 10 0 0 1 10 10 v 24 h -300 z" fill="#1976D2"/>
            </g>
            <text x="480" y="34" font-size="15" fill="#fff" text-anchor="middle" font-weight="bold">B &#183; A band that moves</text>
            <g font-size="12" fill="#fff">
                <rect x="350" y="62" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="376" y="76">spectrum 1</text><circle cx="362" cy="72" r="5" fill="#66BB6A" stroke="#fff"/>
                <rect x="350" y="86" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="376" y="100">spectrum 2</text>
                <rect x="350" y="110" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="376" y="124">spectrum 3</text>
                <rect x="350" y="134" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="376" y="148">spectrum 4</text>
            </g>
            <path d="M 482 72 C 505 74, 505 94, 484 96" fill="none" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <path d="M 482 96 C 505 98, 505 118, 484 120" fill="none" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <path d="M 482 120 C 505 122, 505 142, 484 144" fill="none" stroke="#546E7A" stroke-width="2" marker-end="url(#srA)"/>
            <text x="515" y="104" font-size="12" fill="#0D47A1">fit of the</text>
            <text x="515" y="119" font-size="12" fill="#0D47A1">one before</text>
            <rect x="350" y="166" width="12" height="12" rx="2" fill="#4A7FC1"/>
            <path d="M 352 172 l 3 3 l 5 -6" fill="none" stroke="#fff" stroke-width="2"/>
            <text x="368" y="177" font-size="11.5" textLength="250" lengthAdjust="spacingAndGlyphs" fill="#37474F">Spectra without peaks: start from the fit before them</text>
            <text x="350" y="200" font-size="12.5" fill="#37474F">1. sort the list in the order of the series</text>
            <text x="350" y="223" font-size="12.5" fill="#37474F">2. peaks on the FIRST spectrum only</text>
            <text x="350" y="246" font-size="12.5" fill="#37474F">3. tick the box above</text>
            <text x="350" y="269" font-size="12.5" fill="#37474F">4. select All (the first one too!)</text>
            <text x="350" y="292" font-size="12.5" fill="#37474F">5. Fit Peaks &#8211; N selected spectra</text>
            <text x="350" y="320" font-size="12" fill="#607D8B" font-style="italic">follows a band far along the series</text>
            <!-- card C: different spectra -->
            <g filter="url(#srShadow)">
                <rect x="650" y="10" width="300" height="330" rx="10" fill="#fff" stroke="#EF6C00"/>
                <path d="M 650 20 a 10 10 0 0 1 10 -10 h 280 a 10 10 0 0 1 10 10 v 24 h -300 z" fill="#EF6C00"/>
            </g>
            <text x="800" y="34" font-size="15" fill="#fff" text-anchor="middle" font-weight="bold">C &#183; Each its own peaks</text>
            <g font-size="12" fill="#fff">
                <rect x="670" y="62" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="696" y="76">raman 1</text><circle cx="682" cy="72" r="5" fill="#66BB6A" stroke="#fff"/>
                <rect x="670" y="86" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="696" y="100">raman 2</text><circle cx="682" cy="96" r="5" fill="#66BB6A" stroke="#fff"/>
                <rect x="670" y="110" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="696" y="124">cd 1</text><circle cx="682" cy="120" r="5" fill="#66BB6A" stroke="#fff"/>
                <rect x="670" y="134" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="696" y="148">cd 2</text><circle cx="682" cy="144" r="5" fill="#66BB6A" stroke="#fff"/>
            </g>
            <rect x="815" y="88" width="120" height="44" rx="6" fill="#FFF3E0" stroke="#EF6C00"/>
            <text x="875" y="106" font-size="12" fill="#BF360C" text-anchor="middle">Auto-Detect</text>
            <text x="875" y="122" font-size="12" fill="#BF360C" text-anchor="middle">Peaks &#8211; N</text>
            <text x="670" y="200" font-size="12.5" fill="#37474F">1. select All</text>
            <text x="670" y="223" font-size="12.5" fill="#37474F">2. Auto-Detect Peaks &#8211; N spectra</text>
            <text x="670" y="246" font-size="12.5" fill="#37474F">    (each spectrum its own peaks)</text>
            <text x="670" y="269" font-size="12.5" fill="#37474F">3. Fit Peaks &#8211; N selected spectra</text>
            <text x="670" y="320" font-size="12" fill="#607D8B" font-style="italic">e.g. Raman and CD together</text>
            <!-- below: why the button is greyed -->
            <rect x="10" y="360" width="940" height="218" rx="10" fill="#FFEBEE" stroke="#C62828"/>
            <text x="30" y="386" font-size="14" fill="#B71C1C" font-weight="bold">Fit Peaks greyed?</text>
            <g font-size="12">
                <rect x="30" y="398" width="130" height="20" rx="3" fill="#fff" stroke="#CFD8DC"/><text x="56" y="412" fill="#2E7D32">&#10003; spectrum 1</text><circle cx="42" cy="408" r="5" fill="#2E7D32"/>
                <rect x="30" y="422" width="130" height="20" rx="3" fill="#fff" stroke="#CFD8DC"/><text x="56" y="436" fill="#90A4AE">spectrum 2</text>
                <rect x="30" y="446" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="56" y="460" fill="#fff">spectrum 3</text>
                <rect x="30" y="470" width="130" height="20" rx="3" fill="#4A7FC1"/><text x="56" y="484" fill="#fff">spectrum 4</text>
            </g>
            <text x="185" y="414" font-size="13" fill="#37474F">Spectra 3 and 4 are selected, but they have no peaks. Spectrum 1 has peaks,</text>
            <text x="185" y="432" font-size="13" fill="#37474F">but it is not selected. The fit has nothing to start from, so Fit Peaks is greyed.</text>
            <text x="185" y="460" font-size="13" fill="#1B5E20" font-weight="bold">Fix &#8211; do one of these:</text>
            <g font-size="13" fill="#1B5E20">
                <text x="185" y="482"><tspan font-weight="bold">A</tspan> &#8211; click spectrum 1 alone; under the peaks table click <tspan font-weight="bold">Copy peaks of spectrum 1</tspan>.</text>
                <text x="205" y="499">Then select 3 and 4 and click <tspan font-weight="bold">Paste peaks of spectrum 1 to the selected spectra (2)</tspan>.</text>
                <text x="185" y="523"><tspan font-weight="bold">B</tspan> &#8211; in the box <tspan font-weight="bold">Fitting</tspan> above Fit Peaks tick <tspan font-weight="bold">Spectra without peaks: start from the fit before them</tspan>;</text>
                <text x="205" y="540">then <tspan font-weight="bold">hold Ctrl and click spectrum 1</tspan> in the list, so that 1, 3 and 4 are selected.</text>
                <text x="185" y="564"><tspan font-weight="bold">C</tspan> &#8211; keep 3 and 4 selected and click <tspan font-weight="bold">Auto-Detect Peaks &#8211; 2 spectra</tspan>.</text>
            </g>
        </svg>
        <h3 id="series-steps">Step by step</h3>
        <ol>
            <li><b>Peaks on one spectrum.</b> Click one spectrum in the list, a clear one; it is
            shown in the plot, and the table of peaks (above Auto-Detect) is its own. Set its peaks
            in any of these ways (see <a href="#adding-peaks">Adding peaks</a>):
                <ul>
                    <li><b>Auto-Detect Peaks</b> fills the table with the bands it finds &mdash;
                    check them: select rows you do not want and click <b>Remove Selected
                    Peak(s)</b>;</li>
                    <li><b>Add via Click</b>: tick it and click on the top of each band in the
                    plot;</li>
                    <li>in the <b>table</b>: double-click a value (position, height, width) to
                    correct it, and choose each peak's <b>Model</b> (Gaussian, Lorentzian,
                    &hellip;).</li>
                </ul>
            Then click <b>Fit Peaks &ndash; 1 spectrum</b>. Correct the peaks until this fit is
            good (the residual small, R&sup2; close to 1).</li>
            <li><b>The other spectra</b>: give them a start in one of the three ways above
            (see the red box in the picture):
                <ul>
                    <li><b>A</b> (the same peaks for all): with the spectrum from step 1 shown, click
                    <b>Copy peaks of &hellip;</b> (under the peaks table); select the other spectra
                    and click <b>Paste peaks of &hellip; to the selected spectra</b>;</li>
                    <li><b>B</b> (a band that moves): in the box <b>Fitting</b>, above Fit Peaks,
                    tick the checkbox <i>Spectra without peaks: start from the fit before them</i>,
                    and in step 3 select the spectrum from step 1 too (hold Ctrl and click it in
                    the list) &mdash; ticking the checkbox alone is not enough;</li>
                    <li><b>C</b> (each its own): select the other spectra and click <b>Auto-Detect
                    Peaks &ndash; N spectra</b>.</li>
                </ul></li>
            <li><b>Select the spectra to fit</b> in the list (<b>All</b> for the whole series;
            Ctrl/Shift+click for some) and click <b>Fit Peaks &ndash; N selected spectra</b>. The
            results are in the tab <b>Series results</b>.</li>
        </ol>
        <p><b>Example</b>: raman_11 has peaks and is fitted (&#10003;); raman_13 &ndash; raman_18
        are selected without peaks &mdash; Fit Peaks is greyed. Either click raman_11 alone, click
        <b>Copy peaks of raman_11</b>, select raman_13 &ndash; raman_18 again and click <b>Paste
        peaks of raman_11 to the selected spectra (6)</b> (A); or tick the checkbox <i>Spectra without
        peaks: start from the fit before them</i> and hold Ctrl and click raman_11 in the list, so
        that raman_11 and raman_13 &ndash; raman_18 are selected (B); or
        click <b>Auto-Detect Peaks &ndash; 6 spectra</b> (C). Then Fit Peaks.</p>
        <p><b>Where each fit starts</b> &mdash; the selected spectra are fitted in the order of the
        spectra list: a spectrum with its own peaks starts from them; one without peaks is left
        out, or &mdash; with the box ticked &mdash; starts from the fit of the selected spectrum
        before it, and that fit becomes its peaks. Tick it only for spectra of the same kind: a
        UV-Vis spectrum started from the fit of a Raman spectrum gives a poor fit (marked
        &#9888;). A line under the button names the spectra that are left out or that start from
        the fit before them. With A and C every spectrum has its own start and they are fitted
        independently on several processor cores (faster); with B one after another, so a band is
        followed even when over the series it moves much further than its own width.</p>
        <p>Fitting some of the spectra again (select them, Fit Peaks) replaces only their results;
        the others keep theirs.</p>
        <p>Fitting time grows quickly with the number of peaks; remove the peaks you do not need
        before fitting a long series.</p>
        <div class="screenshot">
            <img src="$SERIES_OVERVIEW" width="${SERIES_OVERVIEW_W}" height="${SERIES_OVERVIEW_H}" alt="Peak Fitting with a series: the tab Series results, the list of spectra with three selected, and their fits in Overlay" />
            <p class="caption">A fitted series: Series results (left), three spectra selected in the list and shown together with their fits (Overlay); Add for: only these three get the new spectra on OK.</p>
        </div>

        <h3 id="series-results">Series results</h3>
        <p>The tab <b>Series results</b> next to the tab Peaks shows the results of <b>the spectra
        selected in the list</b> beside the plot (the same ones the plot shows; <b>All</b> = the
        whole series). The values have the names of the table of peaks: Center, Height, Width,
        Extra, FWHM, Area, and R&sup2; of the whole fit (1 = perfect). <b>Show</b> chooses how:</p>
        <h4>By peak</h4>
        <p>Shown first. One peak at a time: &#9664; &#9654; go to the previous or next peak (its
        mean position is next to the number). One row per spectrum &mdash; follow a band through
        the series, e.g. how its Center moves with the temperature.</p>
        <div class="screenshot">
            <img src="$SERIES_RESULTS" width="${SERIES_RESULTS_W}" height="${SERIES_RESULTS_H}" alt="The tab Series results shown By peak: Peak 1 of 2, one row per spectrum with Model, Center, Height, Width, Extra, FWHM, Area and R squared" />
            <p class="caption">By peak: peak 1 of the 10 selected spectra, a row for each.</p>
        </div>
        <h4>By spectrum</h4>
        <p>Each selected spectrum with its peaks, the same columns as the table of peaks; R&sup2;
        on the line of the spectrum. &#9662; folds a spectrum up, &#9656; opens it again (it stays
        so when you select other spectra).</p>
        <div class="screenshot">
            <img src="$SERIES_BY_SPECTRUM" width="${SERIES_BY_SPECTRUM_W}" height="${SERIES_BY_SPECTRUM_H}" alt="The tab Series results shown By spectrum: three spectra, each with its peaks below it" />
            <p class="caption">By spectrum: three spectra selected in the list, each with its
            peaks.</p>
        </div>
        <h4>All in one table</h4>
        <p>One row per spectrum with position, FWHM, height and area of every peak side by side
        &mdash; as Export and the Data table get them. Wide for many peaks (scroll to the right).
        Selecting rows here selects the same spectra in the list.</p>
        <div class="screenshot">
            <img src="$SERIES_WIDE" width="${SERIES_WIDE_W}" height="${SERIES_WIDE_H}" alt="The tab Series results shown All in one table: one row per spectrum, the peaks side by side" />
            <p class="caption">All in one table: a row per spectrum, all peaks side by side.</p>
        </div>
        <p>A spectrum <i>not fitted yet</i> or whose fit failed (with the previous-result start,
        the next one then starts from the last good fit) is shown as such, without values.</p>
        <ul>
            <li><b>A poor fit of one spectrum</b>: select it, correct its peaks in the tab Peaks and
            click <b>Fit Peaks &ndash; 1 spectrum</b> &mdash; only its row changes. A spectrum
            fitted on its own is kept here too, also before the others are fitted.</li>
            <li><b>Copy &hellip;</b> next to Fit Peaks (on this tab e.g. <b>Copy peak 1 &ndash; 6
            spectra</b>) copies what is shown, for the selected spectra; <b>Export&hellip;</b>
            saves all in one table, for Excel. <b>Open in the Data table</b> opens the
            <a href="help://user_guide#values-per-spectrum">Data table</a> of the series with these
            columns (p1, p2, &hellip;) next to the values stored with the spectra &mdash; e.g. to
            plot the position of a band against <code>temperature_C</code> or compute a ratio of
            two areas.</li>
        </ul>
        <p>The peaks, the fits and the series results are <b>remembered</b>: open Peak Fitting
        again with the same spectra selected and they are back, with the shown spectrum and the
        start choice (unless the spectra were changed meanwhile, e.g. by a baseline
        correction).</p>

        <h2 id="outputs">Output Options (add new spectra)</h2>
        <p>All optional. When ticked, <b>OK</b> adds new spectra to the main list; the original
        spectra are never changed.</p>
        <ul>
            <li><b>Add spectrum from total fit</b> &mdash; the red total fit, named
            <code>&lt;original label&gt;_fit</code>.</li>
            <li><b>Add spectrum from residual</b> &mdash; data minus fit, named
            <code>&lt;original label&gt;_residual</code>.</li>
            <li><b>Add new spectra from individual peaks</b> &mdash; each peak as its own spectrum,
            named <code>&lt;original label&gt;_peak_01</code>, <code>_peak_02</code>, &hellip;
            (two digits, so they sort correctly).</li>
            <li><b>Add for</b> (with a series): <i>all fitted spectra</i>, or <i>the fitted spectra
            selected in the list</i> beside the plot. The numbers in brackets tell how many spectra
            that is. Spectra that are not fitted get nothing.</li>
        </ul>
        <div class="screenshot">
            <img src="$OUTPUT_OPTIONS" width="${OUTPUT_OPTIONS_W}" height="${OUTPUT_OPTIONS_H}" alt="Output Options check boxes" />
            <p class="caption">Output Options &mdash; tick at least one before OK to add spectra.</p>
        </div>

        <div class="key-feature" id="ok-behavior">
            <h3>What happens when you click OK?</h3>
            <p>Fitting is analysis: it never changes the data or the metadata of your spectra.</p>
            <ol>
                <li><b>No Output Option ticked:</b> nothing is added to the spectra list and
                nothing appears in Operations History. The peaks and fits are still remembered for
                the next time you open Peak Fitting on the same spectra.</li>
                <li><b>Output Options ticked:</b> the chosen spectra (fit, residual, single peaks)
                are added &mdash; for the shown spectrum, or with a series for the spectra chosen in
                <b>Add for</b> &mdash; as one step in Operations History (Undo removes them all).
                Each new spectrum carries in its metadata how it was made: the model, the fitted
                values and the spectrum it came from.</li>
            </ol>
            <p><b>Cancel</b> (or closing the window) adds nothing, but also remembers the peaks and
            fits.</p>
        </div>
        <h2 id="models">Peak shapes</h2>
        <p>The Model of each peak (column 2 of the table). FWHM and area are calculated exactly
        from the fitted values for all four shapes.</p>
        <table style="border-collapse:collapse; width:100%;">
            <tr style="background:#f1f1f1;"><th style="text-align:left; padding:4px 8px;">Model</th><th style="text-align:left; padding:4px 8px;">Parameters</th><th style="text-align:left; padding:4px 8px;">Use when</th></tr>
            <tr><td style="padding:4px 8px;"><b>Gaussian</b></td><td style="padding:4px 8px;">Center, Height, Width (&sigma;)</td>
                <td style="padding:4px 8px;">The broadening comes mostly from the instrument or from a distribution of environments &mdash; the usual case for Raman and IR bands of liquids and solids.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Lorentzian</b></td><td style="padding:4px 8px;">Center, Height, Width (&gamma;, half width at half height)</td>
                <td style="padding:4px 8px;">The broadening comes from the lifetime of the state &mdash; e.g. gas-phase lines; bands with long wings.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Voigt</b></td><td style="padding:4px 8px;">Center, Height, Width (&sigma;), Extra (&gamma;)</td>
                <td style="padding:4px 8px;">Both kinds of broadening together: the exact combination (convolution) of a Gaussian and a Lorentzian. The most realistic shape, and the slowest to fit.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Pseudo-Voigt</b></td><td style="padding:4px 8px;">Center, Height, Width (FWHM), Extra (&eta;, 0&ndash;1)</td>
                <td style="padding:4px 8px;">A fast approximation of Voigt: a mix of a Gaussian and a Lorentzian of the same FWHM; &eta; = 0 is a pure Gaussian, 1 a pure Lorentzian.</td></tr>
        </table>
        <div class="tip">
            <strong>Not sure which to pick?</strong> Start with Gaussian. If the residual shows the
            same pattern on both sides of every band (the data have longer wings than the fit),
            try Pseudo-Voigt or Voigt.
        </div>
        $VOIGT_AREA_FIGURE

        <h2 id="details">How it works &mdash; details</h2>
        <h3>Auto-Detect Peaks</h3>
        <ul>
            <li>The spectrum is first <b>lightly smoothed</b> (a Savitzky&ndash;Golay filter over 7
            points, 2nd order) &mdash; only for finding the peaks; the fit always uses the data
            themselves. So a single noisy point does not pass for a narrow peak, and the height and
            width found are those of the band, not of its noisiest point.</li>
            <li>A maximum is a peak when it stands out (its <i>prominence</i>) by at least 10&nbsp;%
            of the spectrum's range <b>and</b> by at least five times the noise, and is at least 3
            points wide. The noise is estimated from the differences between neighbouring points
            (their median absolute value), so it does not depend on the bands.</li>
            <li>A <b>negative</b> peak (a band pointing down, e.g. in CD or difference spectra) must
            in addition lie that much <b>below the baseline</b> (the median of the spectrum): the
            dip between two neighbouring positive bands is not taken for a negative peak.</li>
            <li>Each peak starts as a Gaussian with the height found and the width measured at
            half height: &sigma; = FWHM &divide; 2.355.</li>
            <li>A peak added by a click gets &sigma; from the width at half height of the band under
            the click (the highest point within a few points of the click); where that cannot be
            measured (a shoulder, flat baseline) it gets the initial width (right-click
            Auto-Detect Peaks).</li>
        </ul>
        <h3>The fit</h3>
        <ul>
            <li>All peaks of a spectrum are fitted together by non-linear least squares
            (<i>scipy.optimize.curve_fit</i>, trust-region reflective method, with bounds). The
            model is the sum of the peaks; there is no baseline term.</li>
            <li>The bounds keep the fit within the data: |height| &le; 3&times; the largest
            |value| of the spectrum (and &ge; 0 or &le; 0 with the Amplitude Constraint of that
            spectrum), centre
            within &plusmn;2 widths of its start and within the x range, width up to 10&times; its
            start and at most half the x range.</li>
            <li><b>R&sup2;</b> = 1 &minus; (sum of squared residuals) / (sum of squared deviations
            of the data from their mean): 1 is a perfect fit. Below 0.9 the fit is marked &#9888;
            in the list.</li>
            <li>FWHM and area are calculated exactly from the fitted values for all four shapes
            (Voigt: from the Faddeeva function).</li>
        </ul>
        <h3>Several spectra</h3>
        <ul>
            <li>Every spectrum keeps its own peaks; the table always shows those of the shown
            spectrum. Changing the peaks of a fitted spectrum marks its fit as not fitted yet,
            so a result in Series results always belongs to the peaks shown.</li>
            <li>When every selected spectrum has its own peaks, they are fitted independently, in
            several worker processes at once (the program's Parallel processing setting, see the
            User Guide); otherwise one after another, in the order of the spectra list.</li>
            <li>The peaks, fits, the shown spectrum and your settings are remembered with the
            window for the same selection of spectra; after an operation that changed the spectra
            (e.g. a baseline correction) the old fits are dropped.</li>
        </ul>
    </body>
    </html>
    """)

    return help_template.safe_substitute(images)
