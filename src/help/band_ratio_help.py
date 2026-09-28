# src/help/band_ratio_help.py

"""
Help content for the Band Ratio / Peak Area Calculator operation.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "band_ratio")

_SCREENSHOT_FILES = {
    "OVERVIEW":       "dialog_overview.png",
    "BAND_CONFIG":    "band_config.png",
    "RANGE_DIALOG":   "define_spectral_range_dialog.png",
    "PREVIEW":        "preview_tab.png",
    "RESULTS":        "results_tab.png",
    "PLOTS":          "plots_tab.png",
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


def get_band_ratio_help_title():
    return 'Band Ratio / Peak Area Calculator — Help'


def get_band_ratio_help_content():
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which
    # would collide with .format()-style placeholders.
    help_template = Template("""
    <html><head><style>
        body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
        h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
        h2    { color: #1565C0; margin-top: 22px; }
        h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
        .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        .note { background: #E3F2FD; border-left: 4px solid #1565C0; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        .warn { background: #FFF8E1; border-left: 4px solid #F9A825; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        .fm   { font-family: monospace; background: #ececec; padding: 1px 5px; border-radius: 3px; }
        table { border-collapse: collapse; width: 100%; margin: 8px 0; }
        th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
        td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
        ul,ol { padding-left: 20px; } li { margin: 3px 0; }
        hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        .screenshot { margin: 12px 0; text-align: center; }
        .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
        .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
    </style></head><body>

    <h1>Band Ratio / Peak Area Calculator</h1>

    <p>Computes a scalar value for each spectrum from one or two spectral
    bands and produces a results table.  Each band is defined by one or
    more spectral sub-ranges (include or exclude), exactly as in the 2D Map
    arithmetic mode.  The result column can be Band A alone, the ratio
    A&nbsp;/&nbsp;B, the difference A&nbsp;&minus;&nbsp;B, or the sum
    A&nbsp;+&nbsp;B.</p>

    <div class="note">
        <strong>Non-destructive:</strong> this operation never modifies
        spectrum data.  Results are stored in spectrum metadata and
        exported to CSV for use in external software.
    </div>

    <div class="screenshot">
        <img src="$OVERVIEW" width="${OVERVIEW_W}" height="${OVERVIEW_H}" alt="Band Ratio dialog: Band A/B, Operation, and Selected spectra panels on the left, Preview/Results/Plots tabs on the right" />
        <p class="caption">The full Band Ratio dialog: band and spectrum controls on the left, Preview/Results/Plots tabs on the right.</p>
    </div>

    <hr>
    <h2>Workflow</h2>
    <ol>
        <li>Click <strong>Configure Band A&hellip;</strong> to define the
            spectral ranges for Band A using the range dialog
            (same as the 2D Map band dialog).</li>
        <li>Choose a <strong>metric</strong> for Band A.
            <em>Baseline-corrected integral</em> is recommended for most
            Raman bands.</li>
        <li>Choose the <strong>operation</strong> first — Band B appears
            automatically when A&nbsp;/&nbsp;B, A&nbsp;&minus;&nbsp;B or
            A&nbsp;+&nbsp;B is selected. Configure it the same way.</li>
        <li>Watch the <strong>Preview</strong> tab — the shaded area shows
            exactly what will be integrated, and the drop-line baseline is
            shown as a dashed line. For large datasets (&gt;200 spectra)
            the preview shows the mean &plusmn;&nbsp;SD band instead of
            all individual spectra for performance.</li>
        <li>Switch to the <strong>Results</strong> tab — values are computed
            automatically when you open it.</li>
        <li>Switch to the <strong>Plots</strong> tab for a bar/trend chart
            of Value A, Value B, and the Result across all spectra.</li>
        <li><strong>Copy to clipboard</strong> or <strong>Export
            CSV&hellip;</strong> for use in Excel, Origin, or statistical
            software.</li>
    </ol>

    <div class="tip">
        <strong>OK vs. Cancel vs. closing the dialog.</strong> Band A / Band B
        ranges, metric, and operation are remembered the next time this dialog
        is opened for the same spectra selection, regardless of whether it was
        last closed with <strong>OK</strong>, <strong>Cancel</strong>, or the
        window's own close button. Only <strong>OK</strong> actually commits the
        ratio &mdash; it writes the computed values into each spectrum's
        metadata and records the operation in Operations History, the same role
        Apply / Add as New plays in other dialogs. Cancel and the close button
        both discard that commit but still keep the settings for next time.
    </div>

    <div class="screenshot">
        <img src="$BAND_CONFIG" width="${BAND_CONFIG_W}" height="${BAND_CONFIG_H}" alt="Band A, Band B, and Operation groupboxes with Configure buttons and metric dropdowns" />
        <p class="caption">Band A / Band B configuration and the Operation dropdown that reveals Band B.</p>
    </div>

    <hr>
    <h2>Band definition</h2>

    <div class="warn">
        <strong>A range must be defined.</strong> At least one spectral
        sub-range is required for each active band. The dialog will not
        accept an empty band definition. Results and Plots tabs show a
        warning instead of computing until a range is configured.
    </div>

    <p>Each band is defined in the <strong>Configure Band dialog</strong>
    (the same dialog used for 2D Map spectral ranges).  You can define
    multiple sub-ranges for each band:</p>
    <ul>
        <li><strong>Include mode</strong> &mdash; only the listed ranges
            are used.  Multiple ranges are summed, so you can combine
            several non-contiguous spectral windows into one band
            (e.g. 1000&ndash;1050 + 1100&ndash;1150 cm&sup1;).</li>
        <li><strong>Exclude mode</strong> &mdash; everything outside the
            listed ranges is used.  Useful for removing a known interference
            peak from a broad band.</li>
    </ul>

    <div class="screenshot">
        <img src="$RANGE_DIALOG" width="${RANGE_DIALOG_W}" height="${RANGE_DIALOG_H}" alt="Define Spectral Range dialog with Include/Exclude mode and a list of sub-ranges" />
        <p class="caption">The Define Spectral Range dialog, opened by Configure Band A&hellip; (Configure Band B&hellip; opens the same dialog).</p>
    </div>

    <hr>
    <h2>Metrics</h2>

    <table>
        <tr><th>Metric</th><th>Description</th><th>When to use</th></tr>
        <tr>
            <td><strong>Baseline-corrected integral</strong></td>
            <td>Area above a straight drop-line connecting the first and last
                points of the band region, integrated with the trapezoidal
                rule.</td>
            <td>Default for Raman and IR bands sitting on a sloped
                background. Removes the contribution of the local baseline
                without requiring a separate baseline correction step.</td>
        </tr>
        <tr>
            <td><strong>Integral</strong></td>
            <td>Raw area under the curve (trapezoidal rule).
                Includes any baseline offset.</td>
            <td>Data already baseline-corrected, or when total intensity
                is wanted rather than net peak area.</td>
        </tr>
        <tr>
            <td><strong>Mean</strong></td>
            <td>Average y-value within the band region.</td>
            <td>Quick intensity comparison when band width is constant
                across spectra.</td>
        </tr>
        <tr>
            <td><strong>Peak intensity</strong></td>
            <td>Maximum y-value within the band region.</td>
            <td>Sharp, well-resolved peaks where height is more
                reproducible than area.</td>
        </tr>
        <tr>
            <td><strong>Peak position</strong></td>
            <td>x-value at the intensity maximum.</td>
            <td>Tracking band shifts across a series.</td>
        </tr>
        <tr>
            <td><strong>Variance</strong></td>
            <td>Statistical variance of y-values in the region.</td>
            <td>Assessing noise level or band width variation.</td>
        </tr>
        <tr>
            <td><strong>Intensity at x</strong></td>
            <td>Intensity (y-value) at the single point nearest to the
                specified x position. No range definition needed &mdash;
                Configure Band is replaced by an x-position spinbox.
                Shown in the preview as a dashed vertical line with a
                dot marker.</td>
            <td>Reading off intensity at a specific wavenumber, or
                combining with an integral metric for Band B (e.g.
                peak height / area ratio).</td>
        </tr>
    </table>

    <hr>
    <h2>Operations</h2>

    <table>
        <tr><th>Operation</th><th>Formula</th><th>Typical use</th></tr>
        <tr><td><strong>A only</strong></td><td>value_A</td>
            <td>Absolute band intensity or area</td></tr>
        <tr><td><strong>A / B</strong></td><td>value_A &divide; value_B</td>
            <td>Band ratio (concentration-independent comparison)</td></tr>
        <tr><td><strong>A &minus; B</strong></td><td>value_A &minus; value_B</td>
            <td>Difference between two bands</td></tr>
        <tr><td><strong>A + B</strong></td><td>value_A + value_B</td>
            <td>Combined intensity of two bands</td></tr>
    </table>

    <div class="warn">
        <strong>A / B gives NaN if Band B = 0.</strong> This can happen if
        the band region is outside the spectrum x-range or if the metric
        evaluates to zero. Check the Value B column in the Results table
        for zero or blank entries.
    </div>

    <hr>
    <h2>Practical tips</h2>

    <div class="tip">
        <strong>Use the Preview tab to verify your band definitions.</strong>
        The shaded region shows exactly what is integrated. The dashed line
        is the drop-line baseline for the baseline-corrected integral metric.
        Adjust the sub-range boundaries until the shaded area cleanly covers
        the peak without including neighbouring peaks or obvious artefacts.
    </div>

    <div class="tip">
        <strong>Multiple sub-ranges per band.</strong> If your target band
        overlaps with an interfering peak, define two sub-ranges that bracket
        the interference. The contributions from all sub-ranges are summed
        automatically.
    </div>

    <div class="tip">
        <strong>Normalise before ratios</strong> if you want results
        independent of total intensity. Ratios from unnormalised spectra
        reflect both band shape and overall intensity level.
    </div>

    <div class="screenshot">
        <img src="$PREVIEW" width="${PREVIEW_W}" height="${PREVIEW_H}" alt="Preview tab with the shaded band region, dashed drop-line baseline, and Show band definitions / Show legend checkboxes" />
        <p class="caption">The Preview tab: shaded band region, drop-line baseline, and display options.</p>
    </div>

    <hr>
    <h2>Preview options</h2>
    <ul>
        <li><strong>Show band definitions</strong> (checkbox in Preview tab) &mdash;
            uncheck to hide the Band A / B configuration panels and give
            the preview plot more vertical space.</li>
        <li><strong>Show legend</strong> &mdash; overlays spectrum labels on the
            preview plot. Only shown for small datasets (&le;&nbsp;30 spectra).</li>
    </ul>

    <div class="screenshot">
        <img src="$RESULTS" width="${RESULTS_W}" height="${RESULTS_H}" alt="Results tab with Spectrum, Value A, Value B, and Result columns" />
        <p class="caption">The Results tab: one row per spectrum, with Copy to clipboard and Export CSV.</p>
    </div>

    <hr>
    <h2>Plots tab options</h2>
    <table>
        <tr><th>Option</th><th>Description</th></tr>
        <tr><td><strong>Plot type</strong></td>
            <td>Bar, Line, Scatter, or Bar&nbsp;+&nbsp;Line.</td></tr>
        <tr><td><strong>Label rotation</strong></td>
            <td>0&deg;, 45&deg; or 90&deg; rotation for x-axis tick labels.</td></tr>
        <tr><td><strong>Show last N chars</strong></td>
            <td>Truncate spectrum labels to the last N characters.
                Useful when labels share a long common prefix.
                Set to 0 (shown as <em>all</em>) to display the full label.</td></tr>
    </table>

    <div class="screenshot">
        <img src="$PLOTS" width="${PLOTS_W}" height="${PLOTS_H}" alt="Plots tab with a bar/trend chart of Value A, Value B, and Result, plus plot type and label options" />
        <p class="caption">The Plots tab: Value A, Value B, and Result plotted across all spectra.</p>
    </div>

    <hr>
    <h2>Intensity at x — behaviour at spectrum edges</h2>
    <p>The x&nbsp;position spinbox is initialised to approximately 1/3 of
    the x-axis range for Band A and 2/3 for Band B. If the entered value
    lies outside the spectrum x-range (or in an excluded region), the
    algorithm snaps to the nearest available data point. This is always
    correct behaviour because the x-axis is discrete and spectra may
    have excluded regions. The preview shows the actual snapped position
    as a dashed vertical line with a dot marker.</p>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    the spectrum list, the Results table's Spectrum column, the preview plot's legend, and the Plots tab's x-axis labels.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body></html>
    """)

    return help_template.safe_substitute(images)
