# src/help/melting_curve_help.py

"""
Help content for Melting Curve Analysis.
This module contains detailed help information that can be reused across the application.
"""

import os
import struct
from pathlib import Path
from string import Template

# NOTE: adjust this import to match wherever resource_path() actually lives
# in your project — matches the same pattern baseline_correction_help.py uses.
from src.modules.utils.resource_path import resource_path


# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "melting_curve_analysis")

_SCREENSHOT_FILES = {
    "OVERVIEW":         "dialog_overview.png",
    "SAVED_FITS":       "saved_fits_group.png",
    "SHOW_SUMMARY":     "show_summary_window.png",
    "SHOW_OVERLAY":     "show_overlay_plot_window.png",
    "CURVE_DATA":       "curve_data_table.png",
    "CURVE_EXTRACTION": "curve_extraction_group.png",
    "NORMALIZATION":    "normalization_group.png",
    "SIGMOID_FIT":      "sigmoid_fit_group.png",
    "THERMO_TABLE":     "per_component_thermodynamics_table.png",
    "PLOT_PANELS":      "plot_panels_full_fit.png",
    "OUTPUT_OPTIONS":   "output_options_group.png",
    "BASELINE_CROSS_WARNING": "baseline_crossing_warning.png",
    "UNPHYSICAL_FIT_WARNING": "unphysical_fit_warning.png",
    "NASTY_VS_CLEAN":   "nasty_vs_clean_curve_262_vs_300.png",
    "R2_SCAN":          "r2_vs_wavelength_scan.png",
}

# Cap displayed screenshot width at this many pixels. Qt's rich-text engine
# (what show_help_window renders into) doesn't reliably honor CSS
# "max-width: 100%" on <img> the way a real browser does, so a screenshot
# saved at its native size (e.g. a 1900px-wide capture) shows up at full
# native size and forces a horizontal scrollbar. Setting explicit width/
# height attributes (computed below, aspect ratio preserved) is what
# actually constrains it in Qt. Tune this to comfortably fit your help
# window's content area (window width minus body margin/padding).
_MAX_IMG_WIDTH = 700


def _png_size(path):
    """
    Return (width, height) in pixels for a PNG, read straight from its
    IHDR chunk — avoids needing Pillow just to check dimensions.
    """
    with open(path, "rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a readable PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _resolve_screenshot_uris():
    """
    Resolve each help screenshot to a file:// URI via resource_path(), plus
    an explicit display width/height (capped at _MAX_IMG_WIDTH, aspect ratio
    preserved) so every <img> tag renders at a sane, consistent size instead
    of at the screenshot's raw captured resolution.
    """
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
            # (e.g. a fresh checkout without the images yet) — fall back to
            # a fixed box instead of crashing the whole help page.
            display_w, display_h = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)

        values[f"{key}_W"] = str(display_w)
        values[f"{key}_H"] = str(display_h)

    return values


def get_melting_curve_help_title():
    return "Melting Curve Analysis Help"


def get_melting_curve_help_content():
    """Return HTML content for comprehensive user guide help."""

    images = _resolve_screenshot_uris()

    # Using string.Template ($NAME placeholders) instead of str.format()/
    # f-strings on purpose: the CSS block below is full of literal { }
    # braces, which would collide with .format()-style placeholders.
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
            table.data-table { border-collapse: collapse; margin: 12px 0; width: 100%; font-size: 0.95em; }
            table.data-table th, table.data-table td { border: 1px solid #dee2e6; padding: 6px 10px; text-align: left; }
            table.data-table th { background-color: #e3f2fd; }
            table.data-table td.num { text-align: center; }
        </style>
    </head>
    <body>
        <h1>Melting Curve Analysis Help</h1>

        <h2>Overview</h2>
        <p>This tool builds and analyzes a thermal <b>melting curve</b> from a series of spectra recorded at different temperatures. It reads one signal value from each selected spectrum at a chosen x-position (e.g. a wavenumber or band), plots that value against temperature, and lets you:</p>
        <ul>
            <li><b>Normalize</b> the curve using linear (or constant) approximations of the low- and high-temperature baseline regions.</li>
            <li>Compute <b>thermodynamic parameters</b> (deltaH, deltaS, and the melting temperature Tm) from an Arrhenius-style analysis of the normalized curve.</li>
            <li>Fit the curve as a sum of up to <b>4 sigmoidal transitions</b>, generalizing the two-state model to multiphasic melting behavior &mdash; with each transition getting its own Arrhenius plot and its own deltaH/deltaS/Tm.</li>
        </ul>
        <p>Select two or more spectra (each representing one temperature point) before opening this dialog.</p>

        <div class="screenshot">
            <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="Melting Curve Analysis dialog overview" />
            <p class="caption">The full dialog: controls on the left, curve/fit plots on the right.</p>
        </div>

        <div class="tip">
            <strong>This dialog remembers its settings — however you close it.</strong> Reopening it for the same selection of spectra restores everything from last time — temperatures, extraction/normalization settings, and any fit — so you can pick up right where you left off, <b>regardless of whether it was last closed with OK, Cancel, or the window's own close button</b>. If the underlying spectra are exactly unchanged since you last closed it, this restore is near-instant (the previous curve/fit is reused directly rather than recomputed from scratch); if you changed the spectra in the meantime (e.g. applied a baseline correction), it's detected automatically and everything recomputes properly instead. Only <b>OK</b> actually creates any new spectra, and only if at least one Output Option is checked (see "What Happens When You Click OK?" below) — Cancel and the close button both skip that step but still keep everything you had on screen for next time. If you'd rather discard edited temperatures and start over from the values originally guessed from the spectra's labels, use <b>"Reset"</b> (see Curve Data below).
        </div>
        <div class="tip">
            <strong>The mouse wheel only ever scrolls the panel.</strong> Hovering over a spin box, dropdown, or slider while scrolling never changes its value here (Qt's own default behavior does, which made it unclear what had just changed) — scroll anywhere in the control panel to move through it, without worrying about the cursor's exact position.
        </div>
        <div class="tip">
            <strong>No data of your own yet?</strong> <b>Help &rarr; Test datasets &rarr; Synthetic &rarr; Melting curve &mdash; 1/2/3 transitions, clean/noisy</b> ships six ready-made workbooks built for this tool specifically (1, 2, or 3 known thermal transitions each). Each workbook's Info sheet records the true Tm/deltaH/deltaS/factor per transition to compare a fit against, plus its own <b>recommended extraction X</b> and the wavelength(s) of any <b>isosbestic points</b> to avoid &mdash; unlike a simple fixed-wavelength test signal, these have a genuinely wavelength-dependent spectrum, so the extraction wavelength actually matters: try the recommended X first, then compare against an isosbestic point to see one transition nearly disappear while the other stays visible.
        </div>

        <h2>Recommended Workflow</h2>
        <div class="key-feature">
            <h4>Everything here is real time</h4>
            <p>There's no "Extract Curve" button — the curve builds and rebuilds itself automatically as you work. Two different things trigger this, and it's worth knowing which is which:</p>
            <ul>
                <li>Changing <b>X</b>, the <b>Averaging window</b>, <b>Sheet</b>, or the <b>Source</b> re-reads from the actual source (the spectra, or the file) — the right thing when the setting that determines what gets extracted has changed.</li>
                <li>Hand-editing a cell in the Curve Data table just rebuilds the curve from the table's current contents, without touching the source — this matters in "From file" mode especially, since re-reading the file would otherwise silently overwrite the very correction you just made.</li>
            </ul>
        </div>
        <ol>
            <li>Check the <b>Temperature</b> column in the source table. It is pre-filled by guessing the first number found in each spectrum's label &mdash; <b>always verify and correct these values</b> before proceeding.</li>
            <li>Set the x-value to <b>extract</b> the signal at &mdash; the curve builds itself automatically as soon as there's enough data, no button to click.</li>
            <li>(Optional) Choose a normalization method and adjust the Low-T / High-T region ranges (typing, dragging a slider, or the interactive 'b'-key picker) &mdash; the normalized curve updates live, no separate "apply" step needed.</li>
            <li>Set the number of sigmoid <b>Components</b> (1&ndash;4), optionally click <b>Auto-detect Transitions</b> for initial guesses, then click <b>Fit</b> &mdash; this is also how to get deltaH/deltaS/Tm for a single two-state transition (Components = 1).</li>
            <li><b>Select at least one "Output Option"</b> if you want to keep anything from this analysis &mdash; see below for exactly what happens if you don't.</li>
            <li>(Optional) Click <b>Save Current Fit</b> to keep a copy of this result in the Saved Fits list for later comparison — independent of Output Options/OK.</li>
            <li>Click <b>OK</b> to finish.</li>
        </ol>

        <h2>The Interface Explained</h2>

        <h3>Saved Fits &mdash; comparing results across sessions</h3>
        <p>This dialog always works on <b>one melting curve at a time</b> &mdash; extract, normalize, fit, exactly as described below. <b>Saved Fits</b> is a separate, lightweight container for keeping a copy of a finished result around for comparison, independent of whatever curve you're currently working on. It's included whenever you save a <b>Snapshot</b> and restored when you load one back — unlike the many small "remembered settings" caches elsewhere in this app, this container holds results you deliberately chose to keep, so it survives closing and reopening SpecAnalytiXBase itself, not just this dialog. It's only ever cleared by <b>Remove Selected</b> / <b>Remove All</b> below.</p>

        <div class="screenshot">
            <img src="$SAVED_FITS" width="$SAVED_FITS_W" height="$SAVED_FITS_H" alt="Saved Fits group, expanded" />
            <p class="caption">The Saved Fits group, expanded (click the &#9654;/&#9660; toggle to show/hide it).</p>
        </div>

        <ul>
            <li><b>Save Current Fit:</b> snapshots everything about the curve you're working on right now (extraction, normalization, fit, thermodynamics) under a name you choose. It does <b>not</b> save any spectra &mdash; that's still only ever done via Output Options + OK, exactly as before.</li>
            <li><b>Rename:</b> renames the selected saved fit(s) — or all of them if none are selected — via an editable table with Excel-like Ctrl+C/Ctrl+X/Ctrl+V/Delete, the same as SpecAnalytiXBase's own rename dialog.</li>
            <li><b>Remove Selected / Remove All:</b> delete entries from the container entirely (asks for confirmation first).</li>
            <li><b>Show Summary:</b> opens a full comparison window for every <b>checked</b> saved fit &mdash; see below.</li>
            <li><b>Show Overlay Plot:</b> plots every checked saved fit's normalized curve and sigmoid fit line superimposed on one set of axes, color-coded with a legend — see below.</li>
        </ul>
        <div class="key-feature">
            <h4>The checkbox next to each entry</h4>
            <p>Controls whether that fit is included the next time you click <b>Show Summary</b> or <b>Show Overlay Plot</b> &mdash; uncheck any you want to leave out of the comparison without deleting them. This is separate from clicking/selecting an entry in the list, which is what <b>Remove Selected</b> acts on.</p>
        </div>
        <div class="key-feature">
            <h4>Show Overlay Plot</h4>
            <p>A direct visual complement to Show Summary's numbers: every checked fit's data points and total sigmoid fit line, superimposed on one plot, each in its own consistent color with a legend. <b>"Show data points"</b> and <b>"Show fit lines"</b> can be toggled independently. Useful for spotting SHAPE differences between samples — how sharp a transition is, how many transitions there visibly are, how well-separated they look — that a table of Tm/deltaH/deltaS numbers alone doesn't convey.</p>

            <div class="screenshot">
                <img src="$SHOW_OVERLAY" width="$SHOW_OVERLAY_W" height="$SHOW_OVERLAY_H" alt="Show Overlay Plot window" />
                <p class="caption">Show Overlay Plot: several saved fits' curves and fit lines superimposed, color-coded.</p>
            </div>
        </div>
        <div class="key-feature">
            <h4>The Summary window</h4>
            <p>A sortable <b>table</b> with one row per fitted component across every checked fit (fraction, midpoint, width, deltaH, deltaS, Tm, <b>span</b>, overall R&sup2;/RMSD, source, normalization method) &mdash; a fit that hasn't been through Sigmoid Fit yet gets one mostly-blank row instead. <b>Span</b> is the total signal change across that transition on the <i>original</i> (un-normalized) scale &mdash; the vertical distance between the high-T and low-T baselines at that transition's Tm &mdash; matching the same "span" quantity the original prototype's own baseline-normalization reference figure defines; only available once a normalization method has been applied.</p>

            <div class="screenshot">
                <img src="$SHOW_SUMMARY" width="$SHOW_SUMMARY_W" height="$SHOW_SUMMARY_H" alt="Show Summary window" />
                <p class="caption">Show Summary: the comparison table plus one of its chart types.</p>
            </div>

            <p>Below the table, <b>Plot type</b> chooses how to compare the checked fits:</p>
            <ul>
                <li><b>Bar (1 property):</b> one bar per component across every checked fit, colored by which fit it came from.</li>
                <li><b>Bar (grouped by component):</b> one group of bars per fit, one bar per component within each group &mdash; colored consistently <i>by component number</i> instead (component 1 red, 2 green, 3 blue, 4 magenta), with each bar's value labeled on top. Good for comparing e.g. "how big was component 1" across every sample at a glance, matching the original prototype's own fraction-comparison bar plots.</li>
                <li><b>Line & points (1 property):</b> the same values as Bar, connected by a dashed line in fit/component order &mdash; matches the original prototype's own "line & points vs sample" style, useful for spotting a trend or an odd jump.</li>
                <li><b>Points with mean/std band:</b> every point for the chosen property against its position in the list, with a dashed mean line and a shaded &plusmn;1 standard deviation band behind them &mdash; matches the original prototype's own mean/std-deviation reference figure, good for spotting outliers at a glance.</li>
                <li><b>Scatter (2 properties):</b> a chosen X property against a chosen Y property, one point per component, colored and directly labeled with its sample/fit name. Error bars are shown automatically for Tm, deltaH, and deltaS wherever a standard-error estimate is available (3+ Arrhenius points).</li>
                <li><b>Scatter (3D, 3 properties):</b> the same idea with a third, Z property &mdash; e.g. Tm vs deltaH vs deltaS at once, each point labeled the same way.</li>
                <li><i>Not yet included:</i> hierarchical clustering/dendrograms &mdash; a substantial separate feature; let me know if you'd like it added.</li>
            </ul>
            <p>For "Scatter (2 properties)" specifically, checking <b>"Show mean/std region"</b> groups points by <i>component number</i> (every fit's component 1 together, every component 2 together, and so on) and shades a mean&plusmn;std rectangle plus dashed crosshairs for each group, in that component's color &mdash; useful for spotting which points sit unusually far from the rest of their group in both dimensions at once.</p>
            <p>For Bar, Line &amp; points, and Points with mean/std band, checking <b>"Sort by value"</b> orders points along the x-axis by ascending property value instead of the order fits were saved in &mdash; e.g. pick Tm and check this to line every sample's transition up from lowest to highest temperature, an easy way to compare "the 1st transition" across samples once components are grouped that way (see above). <b>"Show mean/std region"</b> and <b>"Sort by value"</b> are two independent options for two different plot types, not something to combine &mdash; each is grayed out automatically whenever it wouldn't do anything in the currently selected Plot type, so it's never unclear whether toggling one has any effect.</p>
            <p>Every fit keeps its own consistent color across the "by fit" plot types (Bar and both Scatter modes). <b>Copy Table</b> and <b>Save as CSV...</b> export the table exactly as shown (the underlying data, not the chart).</p>
        </div>

        <h3>Curve Data (Temperature / Signal)</h3>

        <div class="screenshot">
            <img src="$CURVE_DATA" width="$CURVE_DATA_W" height="$CURVE_DATA_H" alt="Curve Data table" />
            <p class="caption">The Curve Data table: Spectrum, X (Temperature), and Y (Signal) columns.</p>
        </div>

        <ul>
            <li>In <b>"From spectra"</b> mode: one row per selected spectrum. X is pre-filled by guessing from each spectrum's label (never trusted as final &mdash; always check it); Y fills in automatically, in real time, by reading the signal at the chosen X position from each spectrum. The <b>Spectrum</b> column shows which row belongs to which spectrum &mdash; uncheck <b>"Show spectrum names"</b> to hide that column if you don't need it.</li>
            <li>In <b>"From file"</b> mode: choosing a file (and Sheet, for Excel) replaces the table's rows automatically with whatever (temperature, signal) pairs were loaded (see Curve Extraction below). The Spectrum column and "Show spectrum names" checkbox are hidden entirely here &mdash; there's no spectrum involved to show.</li>
        </ul>
        <p>Excel-like editing works on both X and Y: select one or more cells and use <b>Ctrl+C</b> (copy), <b>Ctrl+X</b> (cut), <b>Ctrl+V</b> (paste &mdash; a single column fills just that column, a two-column tab-separated block fills X then Y), and <b>Delete</b>/<b>Backspace</b> (clear). Click a column header to sort by it (standard Qt behavior — click again to reverse the direction). <b>"Reset"</b> (next to the "?" help button, above the table) restores every X value to what it was originally guessed as when this dialog was first opened, discarding any edits made since (asks for confirmation first) &mdash; useful to start over from scratch after experimenting with values.</p>
        <p>If two or more rows end up with the same temperature, this dialog asks whether to <b>average</b> their extracted signal into a single point for that temperature (a melting curve needs exactly one signal value per temperature — choose No to cancel and fix the temperatures manually instead). This is never done silently.</p>
        <div class="warning">Switching between "From spectra" and "From file" (see Curve Extraction below) always resets the current curve and fit, then rebuilds automatically under the new source &mdash; a curve built under one source is meaningless under the other, so nothing stale is ever left showing.</div>

        <h3>Curve Extraction</h3>

        <div class="screenshot">
            <img src="$CURVE_EXTRACTION" width="$CURVE_EXTRACTION_W" height="$CURVE_EXTRACTION_H" alt="Curve Extraction group" />
            <p class="caption">Curve Extraction: Source, and the X-value/Averaging window (From spectra mode shown).</p>
        </div>

        <div class="key-feature">
            <h4>Source: From spectra / From file</h4>
            <p>Two radio buttons choose where the curve is built from, and can be switched at any time:</p>
            <ul>
                <li><b>From spectra</b> (default): builds the curve from the selected spectra, using whichever <b>Method</b> is chosen below (Extract signal at X, or SVD).</li>
                <li><b>From file</b>: skip spectra entirely and load an already-built melting curve — temperature and signal pairs — directly from a text or Excel file via the <b>Browse...</b> button. Two columns, Temperature then Signal; plain text files (.txt/.csv/.dat) can be comma-, tab-, or whitespace-separated, and an optional non-numeric header row is detected and skipped automatically. The Method/X-value/Averaging-window rows and the file/Sheet rows are shown only for whichever source is currently selected, not just grayed out &mdash; and the Sheet row only appears at all once an Excel file is loaded.</li>
            </ul>
        </div>

        <div class="key-feature">
            <h4>Method (From spectra only): Extract signal at X / SVD (generalized curve)</h4>
            <p>A second, opt-in way to turn the selected spectra into one melting curve, alongside the app’s original approach — <b>Extract signal at X stays the default</b>; nothing changes unless you switch the <b>Method</b> dropdown.</p>
            <ul>
                <li><b>Extract signal at X</b> (default): reads one signal value from each selected spectrum at the chosen <b>X</b>, optionally averaging over a window around it (<b>Averaging window +/-</b>; 0 = interpolate exactly at X). Simple and transparent, but sensitive to noise or an isosbestic point sitting exactly at that one x position, and requires picking a representative X by hand.</li>
                <li><b>SVD (generalized curve)</b>: ported from this app’s sister tool <b>MeltAnalytiX</b>, and matching the convention SpecAnalytiXBase’s own SVD Analysis tool uses. Instead of one x position, this decomposes the <i>whole</i> (wavelength &times; spectrum) matrix via SVD and uses the first singular component’s own across-spectrum trajectory as the melting curve — a summary of how the entire measured spectral shape changes with temperature, not just one point on it. By default each wavelength’s row is <b>mean-centered</b> (its own across-spectrum average subtracted) before the SVD runs — uncheck <b>"Mean-center each wavelength before SVD"</b> only to compare against the original, uncentered behavior; an uncentered decomposition’s first component tends to just reproduce the plain per-spectrum average rather than the real transition shape.</li>
            </ul>
            <p>SVD mode requires every selected spectrum to share the <i>exact same x-axis grid</i> (identical wavelengths/wavenumbers) — if they don’t, extraction fails with a message naming the mismatched spectrum; re-sample or crop the spectra onto a common grid first, or use Extract signal at X instead, which has no such requirement. After a successful SVD extraction, a small status line reports the explained-variance fraction of the first one or two components (PC1 close to 100% means a single, clean process dominates; a non-trivial PC2 is a hint that more than one process is changing with temperature) and the x-axis range actually used.</p>
            <div class="warning">Everything downstream of extraction — Normalization (including Automatic/Santoro-Bolen mode), Sigmoid Fit, the thermodynamics tables, and every Output Option — works exactly the same regardless of which extraction method built the curve. Only how the raw (temperature, signal) curve itself gets built differs; switching Method at any time resets the current curve/fit and rebuilds automatically under the new one, the same way switching Source does.</div>
        </div>

        <h3>Normalization</h3>

        <div class="screenshot">
            <img src="$NORMALIZATION" width="$NORMALIZATION_W" height="$NORMALIZATION_H" alt="Normalization group" />
            <p class="caption">Normalization: Method, Threshold, the display checkboxes, and the Low-T/High-T region controls.</p>
        </div>

        <p>Approximates the low-temperature ("unfolded" or "folded", depending on the sign of the transition) and high-temperature baseline regions by a constant (zero order) or linear (first order) fit, then computes:</p>
        <p style="text-align:center;"><code>A_corr = (A_orig - A_low) / (A_high - A_low)</code></p>
        <p>The <b>Threshold (span)</b> spinbox next to Method belongs here too, even though it's specifically for the Arrhenius-based analyses further down (Thermodynamic Parameters and Sigmoid Fit's per-component thermodynamics) &mdash; it's treated as part of preparing the curve, shared by both approaches rather than specific to either, so it lives with the rest of curve preparation instead of being nested in one analysis group or the other. See its own "?" button for the full explanation, including what it does and doesn't affect.</p>
        <p>By convention, A_corr always runs from 0 at low temperature to 1 at high temperature, regardless of whether the <i>raw</i> signal rises or falls with temperature &mdash; this is unambiguous and is what the fit and Arrhenius calculation both assume. If you're used to seeing melting curves plotted descending from 1 to 0 instead, check <b>"Invert normalized curve display"</b>: this only flips which end of the y-axis is drawn at the top, so the curve trace looks the way you're used to &mdash; the underlying data, the fit, and every reported number are completely unaffected, since only the picture changes, not the math.</p>
        <p>The Low-T / High-T region boxes default to the outer ~15% of the temperature range on the first extraction &mdash; widen or move them if your baselines are noisier or narrower than that. Every boundary is confined to the curve's own temperature range (a baseline region can't extend past your actual data), and each region's Min can never be dragged past its own Max, or vice versa &mdash; dragging one past the other pushes the other along with it instead, so the two can never end up crossed/inverted. Everything here takes effect immediately &mdash; there's no separate "Apply" button to click.</p>
        <div class="warning">
            <h4>"Normalization Failed" warning</h4>
            <p>If no data points fall inside one or both baseline regions at all, or the data inside them is too degenerate to fit (e.g. too few distinct temperatures, or an all-identical signal), a <b>"Normalization Failed"</b> popup explains which and normalization is skipped &mdash; the raw curve still shows. This is different from the persistent baseline-crossing banner below (which is about an already-successful fit becoming numerically unstable at one point, not a fit that couldn't be computed at all): it only ever appears once, right after opening the dialog or re-extracting the curve, never while dragging a baseline slider &mdash; a popup on every slider frame would be disruptive, so a live drag that transiently produces the same failure fails silently instead, exactly like every other live update here. Seeing this on a series that should be perfectly ordinary spectra is usually a sign the wrong spectra were selected &mdash; for instance, re-analyzing this tool's own previously exported curve/normalized-curve output as if it were a fresh series of temperature spectra.</p>
        </div>
        <div class="warning">
            <h4>When does "None" make sense?</h4>
            <p>Only when the curve is <b>already</b> on roughly a 0&ndash;1 scale &mdash; typically a curve loaded "From file" that was already normalized elsewhere, or one that happens to have flat, unit-scale baselines. The Sigmoid Fit model's component fractions always sum to 1 and each sigmoid saturates within [0, 1], so its total output is structurally confined to roughly that range &mdash; it cannot represent an arbitrary absorbance/intensity scale (e.g. 1.5&ndash;3.0) or curves with real sloped baselines at all, no matter how good the starting guesses are. Fitting with "None" selected on data outside roughly [&minus;0.25, 1.25] (or with too narrow a range) triggers a confirmation warning before proceeding, since the fit will very likely fail to converge or give a meaningless result. For real raw experimental data, use Zero order or First order instead.</p>
        </div>
        <div class="warning">
            <h4>"Low-T and High-T baselines cross" warning — and what it actually excludes</h4>
            <p>Appears (as a persistent banner, not a popup — normalization runs live as you drag the sliders, so a popup on every change would be disruptive) whenever the two fitted baseline lines cross, or come close to crossing, somewhere within the curve's own temperature range. Right at that point, <code>A_high(T) - A_low(T)</code> is at or near zero, and A_corr = (A - A_low) / (A_high - A_low) is dividing by (nearly) zero there — producing huge, physically meaningless excursions in the normalized curve near that temperature, regardless of how good the underlying data or fit is. This is a genuine numerical instability of linear-baseline normalization, not a sign anything is wrong with the fitting step.</p>
            <p><b>These points are excluded from every Arrhenius/van't Hoff fit automatically</b> — not just flagged. Every point whose own <code>|A_high(T) - A_low(T)|</code> falls below 15% of the curve's own largest such value is dropped before the Threshold (span) filter even runs, for the whole-curve calculation and for every component of a multi-transition Sigmoid Fit alike. This matters because a point next to a crossing can have a <i>spurious but perfectly finite</i> A_corr value — nothing about it looks wrong on the normalized curve, so it sails straight through the ordinary Threshold filter (which only looks at how close a point's y-value is to 0 or 1, not at how unstable the DENOMINATOR that produced it was) — and then distorts the regression badly precisely because the transform is most sensitive right where <code>K = A_corr/(1-A_corr)</code> crosses 1, i.e. right at Tm. Left in, one or two such points can drag the fitted deltaH down by an order of magnitude and pull the fitted Tm away from the true value by 10&deg;C or more, while the fit's own R&sup2;/uncertainty numbers just look generically worse rather than pointing at the real cause — confirmed directly on real data. The warning text itself reports how many points were excluded this way, and updates live as you move the baseline sliders.</p>
            <p>The exclusion is <i>not</i> gated on the "crossing" banner appearing at all — two baselines that come close without technically crossing sign are just as unstable near their closest approach, so points there are excluded on the same basis even when no warning is showing. Whenever this happens, cross-check the Sigmoid Fit's own midpoint (an independent nonlinear fit to the same points, not a linear van't Hoff regression) against the Arrhenius Tm below it: for a genuine two-state transition the two should agree closely (see "Real-time sliders" above on X_trans, a third independent check) — a persistent, large disagreement between them, even after this exclusion, is a stronger sign than the warning banner alone that the Low-T/High-T regions don't actually capture a flat plateau for this curve and are worth repositioning.</p>

            <div class="screenshot">
                <img src="$BASELINE_CROSS_WARNING" width="$BASELINE_CROSS_WARNING_W" height="$BASELINE_CROSS_WARNING_H" alt="Baseline-crossing warning banner" />
                <p class="caption">The persistent warning banner shown when the two baselines cross (or nearly cross) within the curve's range, now reporting how many points were excluded.</p>
            </div>
        </div>
        <div class="key-feature">
            <h4>Real-time sliders</h4>
            <p>Each of the four boundaries (Low-T min/max, High-T min/max) has its own slider next to its spin box &mdash; drag one and the shaded region, baseline lines, and normalized curve all update live as you move it. Typing directly into a spin box updates its slider and the plot the same way. The orange/green shaded bands on the plot always show the current selections.</p>
            <p>The Original curve panel's title also shows <b>X_trans</b> once normalization succeeds &mdash; the temperature where the raw curve directly crosses the median line between the two baselines, found by straightforward interpolation over the whole curve, with no regression and no threshold-based point filtering involved at all (see <a href="#impl-xtrans">Implementation Details</a>). This is the "median temperature" reference many two-state UV-melting protocols describe. It will generally sit close to a component's own Arrhenius Tm (see Sigmoid Fit below) for a clean two-state transition, but they are not the same computation and are not guaranteed to agree exactly &mdash; especially if the van't Hoff plot has real curvature a straight-line regression can't capture, or the chosen Threshold pulls in points from a region where that curvature matters. Both are shown so you can compare them directly rather than relying on either alone.</p>
            <p><i>A naming note:</i> "span" is used for two unrelated things in this app &mdash; the Threshold (span) setting above, and the unrelated <b>Span</b> column/property in Show Summary (the vertical distance between the two baselines at a transition's Tm, on the original un-normalized scale). They don't affect each other.</p>
        </div>
        <div class="key-feature">
            <h4>Picking baselines interactively on the plot</h4>
            <p>With <b>"Pick baselines interactively on the plot"</b> checked (default): click the <b>Original curve</b> panel once, use the toolbar's <b>zoom</b> (magnifying glass) or <b>pan</b> tool to frame a baseline region, then press the <code>b</code> key. The framed x-range is captured as the Low-T or High-T region &mdash; whichever it's nearer to by temperature &mdash; so re-picking one region never disturbs the other. Use the toolbar's <b>Home</b> button to return to the full curve view, then repeat for the second region. Requires the Original curve panel to be visible (see "Choosing what to show" above).</p>
        </div>
        <div class="warning">
            <h4>Noisy data needs more attention to Threshold</h4>
            <p>Noisier spectra tend to give noisier low-T/high-T baseline estimates, which in turn makes stray outlier points more likely to show up on the normalized transition curve. Those outliers get hugely <b>amplified</b> once transformed into ln(K) for the Arrhenius analysis below — the transform diverges fastest exactly near the baselines, so a single bad point there can dominate and skew an entire regression line, even though visually it looked like just one point out of many on the normalized curve itself. If deltaH/deltaS/Tm shift by a surprising amount for a small Threshold change (e.g. 0.95 to 0.94), that's usually a sign one or two outlier points were just included or excluded — check the per-component Arrhenius plot (Sigmoid Fit, below) for a point sitting noticeably off the trend the others follow, rather than assuming the underlying fit is unstable. This is exactly why Threshold is adjustable rather than fixed: the "right" span genuinely depends on how clean the data is.</p>
        </div>
        <div class="tip">
            <p><b>Note for anyone who used earlier versions of this tool:</b> a standalone "Thermodynamic Parameters (Arrhenius)" section used to live here, with its own "Compute deltaH, deltaS" button — a whole-curve, single-transition van't Hoff calculation, independent of Sigmoid Fit. It was removed because, for the one case it was ever available (Components = 1), its result is provably identical to Sigmoid Fit's own per-component thermodynamics (see "Thermodynamic parameters (per component)" under Sigmoid Fit below) down to every decimal place — not approximately similar, but the exact same regression on the exact same data (with only one component, there is no "other component's contribution" to subtract during reconstruction, so the per-component calculation reduces algebraically to the whole-curve one; see <a href="#impl-reconstruction">Implementation Details</a>). Keeping two controls, in two different places, for one calculation added GUI clutter without adding any information — Sigmoid Fit (Components = 1) is now the one path to these numbers.</p>
        </div>

        <h3>Automatic (Santoro-Bolen) Mode</h3>
        <p>A second, opt-in <b>Method</b> option alongside the manual Zero order / First order workflow described above — <b>Manual stays the default</b>; nothing about the existing workflow changes unless you switch to it. Ported from this app's sister tool <b>MeltAnalytiX</b> (which analyzes many melting curves at once, batch-style, with no person choosing baseline windows for each one) and adapted here to a single, interactively-reviewed curve.</p>
        <div class="key-feature">
            <h4>What it does differently</h4>
            <p>Manual mode is a <i>two-stage</i> process: you choose Low-T/High-T baseline windows, each gets its own independent straight-line fit, and only <i>then</i> does Sigmoid Fit fit the transition(s) to what's left. Automatic mode instead fits the native-state baseline, the denatured-state baseline, <b>and</b> the transition(s) themselves all in <b>one simultaneous nonlinear regression</b> against the raw curve — a two-state (or, for a genuinely multiphasic curve, shared-baseline multi-state) model, sometimes called a Santoro-Bolen fit. There is no baseline-window-guessing step to get wrong in the first place: the whole curve informs the baselines and the transition together, self-consistently.</p>
            <p>The number of components (1&ndash;4) is chosen for you as well, via the same statistical test (<b>BIC</b>, Bayesian Information Criterion) model-selection problems generally use — walked up one component at a time, starting from 1, each larger fit warm-started from the smaller one's own converged answer, and only adopted when it lowers BIC <i>decisively</i> (the standard Kass &amp; Raftery statistical convention). On top of that, a candidate component count is only accepted if it <i>also</i> doesn't make the resulting van't Hoff/Arrhenius fit or the baseline's own tracking of the real data at the curve's edges meaningfully worse than the best seen so far — plain BIC alone can be fooled by a smooth extra component absorbing structured noise (drift, a slightly imperfect correction) rather than representing a genuine additional transition.</p>
        </div>
        <div class="key-feature">
            <h4>Using it</h4>
            <p>Select <b>"Automatic (Santoro-Bolen fit)"</b> from the Normalization group's <b>Method</b> dropdown. The fit runs immediately (and re-runs automatically whenever the curve, Shape, or Threshold changes). While this mode is active:</p>
            <ul>
                <li>The Low-T/High-T region spin boxes and sliders, and the Sigmoid Fit group's <b>Components</b> spinner and <b>Auto-detect Transitions</b> button, are all disabled — Automatic determines all of them itself. Their values still update to show what Automatic actually settled on (so switching back to Manual afterward starts from a sensible place), they just can't be hand-edited while Automatic is selected.</li>
                <li><b>Shape</b> stays live — switching between Logistic and Error function re-runs the automatic fit with the new shape.</li>
                <li><b>Fit</b> still works — it simply re-runs the same automatic pipeline on demand (e.g. after changing something upstream that doesn't trigger a re-run on its own).</li>
                <li>The <b>guesses/fit-results table</b>, <b>thermodynamics table</b>, plots, <b>Fit Details</b>, <b>Save Current Fit</b>, and every Output Option all work exactly as they do in Manual mode, reading whatever Automatic produced — there is nothing separate to learn for those.</li>
            </ul>
        </div>
        <div class="warning">
            <h4>The reliability banner — read this before trusting a number</h4>
            <p>A colored banner appears above the Low-T/High-T controls whenever Automatic mode is active, in one of three states:</p>
            <ul>
                <li><b style="color:#7f1d1d;">Red — no automatic fit found.</b> The joint regression didn't converge, or was rejected by one of this mode's built-in safety checks (an implausible transition midpoint far outside the measured range, or a fitted baseline that doesn't track the real data closely enough at an edge — usually a sign this curve has no genuine flat plateau for the fit to anchor on). The banner names the specific reason. <b>Nothing is fitted at all in this state</b> — switch to Manual mode and set the baseline windows yourself.</li>
                <li><b style="color:#b45309;">Amber — a fit was found, but didn't pass every reliability check.</b> A number is shown, but treat it with real caution; the banner names exactly which check(s) failed and their actual values, so you can judge for yourself rather than trusting a bare yes/no.</li>
                <li><b style="color:#14532d;">Green — a fit was found and passes every reliability check.</b> The same standard of trust MeltAnalytiX itself requires before treating an automatic result as good.</li>
            </ul>
            <p>The six checks behind the amber/green verdict (a low-confidence or missing value fails its own check, except Tm-in-fit-range, which passes by default when it can't be computed at all, since the two checks right before it already catch the case where the whole regression failed):</p>
            <ol>
                <li>Arrhenius R&sup2; &ge; 0.85</li>
                <li>Tm falls inside the curve's actual measured temperature range</li>
                <li>the Low-T/High-T baselines don't cross near the transition itself (a crossing confined to an already-saturated plateau tail, far from the points the Arrhenius regression actually used, is allowed — same distinction Manual mode's own baseline-crossing warning makes, see above)</li>
                <li>Tm falls inside the actual window of points the Arrhenius regression used (stricter than #2 alone — a shallow, noisy fit can extrapolate its Tm well past its own fit window while still landing inside the curve's overall range)</li>
                <li>the sigmoid shape re-fit's own R&sup2; &ge; 0.70 (a genuine, separate re-fit of the transition shape in normalized space — not the same number as the Arrhenius R&sup2; above, since they can fail for different reasons)</li>
                <li>the fitted baseline tracks the real data within 12% of the curve's own amplitude at both the low- and high-temperature edge</li>
            </ol>
            <p>Automatic mode <b>never silently falls back</b> to a different heuristic on a red or amber result — a rejected or low-confidence fit is exactly the signal to switch back to Manual mode and choose baseline windows yourself, the same way you would have without this feature at all.</p>
        </div>

        <h3>Sigmoid Fit</h3>

        <div class="screenshot">
            <img src="$SIGMOID_FIT" width="$SIGMOID_FIT_W" height="$SIGMOID_FIT_H" alt="Sigmoid Fit group" />
            <p class="caption">Sigmoid Fit: Components/Shape/Auto-detect/Fit/Fit Details, the display checkboxes, and the guesses/results table.</p>
        </div>

        <p>Fits the (normalized, if available; otherwise raw) curve as a weighted sum of 1&ndash;4 sigmoids (Logistic or Error-function shape), each with its own fraction, midpoint (transition temperature), and width. The fractions of all components always sum to 1. Components are always returned sorted by <b>ascending midpoint</b> &mdash; "component 1" is reliably the lowest-temperature transition, "component 2" the next, and so on, regardless of what order they happened to converge in during fitting. This is what makes comparing "the 1st transition" across several different fits in Show Summary meaningful.</p>
        <div class="key-feature">
            <h4>The guesses table</h4>
            <p>Click the <b>&#9660;/&#9654; Starting guesses / fit results</b> toggle to show/hide this table (expanded by default). It always shows the current <b>Fraction/Midpoint/Width</b> for every component — evenly-spaced defaults to begin with, whatever <b>Auto-detect Transitions</b> last estimated, an actual optimizer result once you click <b>Fit</b>, or anything in between once you start hand-editing. <b>Double-click any cell to edit it directly</b> — every edit immediately recomputes and redraws the preview curves on the Normalized (or Original) curve panel, the fit quality line, and the <b>per-component thermodynamics</b> below, all together and live, whether or not a real Fit has ever been run. Standard errors from an actual optimizer run (when available) show up as a tooltip on hover rather than in the cell text itself, so every cell always stays a plain, directly-editable number.</p>
            <p>Whenever the table's current fraction/midpoint/width didn't come from an actual <code>curve_fit</code> optimization — the evenly-spaced defaults, Auto-detect's estimate, or anything you've hand-edited since the last real Fit — the quality line says <b>"(preview — click Fit to optimize)"</b>, and no standard errors are shown (a preview reconstruction has no covariance matrix to draw them from). Clicking <b>Fit</b> always replaces whatever's currently shown with a genuine optimizer result, complete with real parameter uncertainties. Changing <b>Components</b> or <b>Shape</b> resets the table back to fresh evenly-spaced defaults (and their own live preview), since a previous fit or set of guesses for a different number of components no longer applies.</p>
        </div>
        <ul>
            <li><b>Auto-detect Transitions:</b> estimates initial midpoints from peaks in the curve's smoothed derivative and writes them straight into the guesses table (with default width and equal fractions) &mdash; run this before Fit when using more than one component, since the fit is sensitive to good initial guesses. Edit any cell afterward if the estimates aren't quite right.</li>
        </ul>
        <div class="tip">
            <h4>The short version, before the details below</h4>
            <p>Only <b>one</b> thing actually determines whether Sigmoid Fit will struggle: <b>is the NORMALIZED curve (not the raw one) rising the whole way, with no dips or reversals?</b> That's the entire question. Everything below is just explaining <i>why</i> that can fail and what causes it, but if you only remember one thing, remember this one.</p>
            <p>How the pieces relate to each other:</p>
            <ul>
                <li><b>A non-monotonic normalized curve</b> is the actual problem &mdash; not a symptom of something else, the thing itself.</li>
                <li><b>"Mixed-sign transitions"</b> is just another name for the same thing, seen from a different angle: add up several always-rising curves and the sum always rises too; the only way to get a dip is if some pieces pull the opposite way. A dip and a sign-mix are the same fact described two ways, not two separate conditions.</li>
                <li><b>Real competition between transitions</b> (one species converting into another) is <i>one</i> possible reason a dip shows up &mdash; but not the only one. Fully independent transitions, observed at an unlucky extraction wavelength, can produce the exact same dip (see the worked example below). Seeing a dip does not by itself prove real competition is happening.</li>
                <li><b>Baselines crossing</b> is a side-effect that tends to tag along with a severe dip, not a cause of the fitting problem itself &mdash; it's a separate, numerical issue in the normalization step (see below for why).</li>
            </ul>
            <p><b>Important:</b> the RAW curve is allowed to be non-monotonic (a real hump, a hollow — whatever the actual raw signal does) with no issue at all, <i>as long as</i> that shape doesn't survive into the normalized curve. Baseline correction can "absorb" a raw wiggle that's confined to a flat, mostly-noise region without disturbing the fit — the trouble only starts once the wiggle overlaps the actual transition and comes through into the normalized 0-1 curve too, usually at a similar or even exaggerated size relative to the raw curve.</p>
        </div>
        <div class="warning">
            <h4>This model assumes independent transitions — and can look "successful" even when that's wrong</h4>
            <p>Every component here is a monotonic sigmoid (0 to 1 as temperature increases), and their fractions are meant to be non-negative and sum to 1 &mdash; together, this represents <b>N independent, non-interacting two-state transitions happening in parallel</b>. It does <b>not</b> represent a transition where one species genuinely converts into another (population transferred between them) &mdash; e.g. a sequential A&rarr;B&rarr;C pathway, where an intermediate species' own population would rise and then fall. No combination of non-negative-weighted monotonic sigmoids can ever produce that rise-then-fall shape, no matter how the parameters are tuned. In terms of the underlying two-state equation for each transition (<code>f<sub>i</sub> / (1 + exp(-(T - Tm<sub>i</sub>)/lambda<sub>i</sub>))</code>), this model implicitly requires every transition's lambda<sub>i</sub> to have the <b>same effective sign</b> once the curve is normalized 0-1 &mdash; each term individually increasing. Since normalization (see above) always converts the whole curve to run 0-to-1 regardless of which way the raw signal moved, a set of genuinely independent transitions that ALL push the raw signal the same direction (all-positive or all-negative lambda before normalization) still normalizes correctly into this same-sign, fittable form; it's specifically a MIX of signs after normalization — one transition's contribution effectively working against another's at the wavelength you extracted &mdash; that this model cannot represent.</p>
            <p>With 3 or more components, this tool's fit can still <i>numerically</i> converge on such a curve anyway — not by representing the true shape correctly, but by pushing one component's fraction to something impossible for a real population (negative, or collapsed to zero), while <code>curve_fit</code> reports a high R&sup2; regardless. A warning appears after Fit if any component's fraction comes back negative or has collapsed to essentially zero. With exactly 2 components this particular failure mode can't happen &mdash; simple arithmetic, not anything about the curve's shape: the second fraction is always <code>1 - f<sub>1</sub></code>, and since <code>f<sub>1</sub></code> is already constrained to [0, 1], <code>1 - f<sub>1</sub></code> is automatically in [0, 1] too. With 3+ components, two or more fractions are each individually constrained to [0, 1], but nothing stops their SUM from exceeding 1 &mdash; when it does, the remaining (derived) fraction is forced negative.</p>

            <div class="screenshot">
                <img src="$UNPHYSICAL_FIT_WARNING" width="$UNPHYSICAL_FIT_WARNING_W" height="$UNPHYSICAL_FIT_WARNING_H" alt="Unphysical fit result warning" />
                <p class="caption">The warning shown after Fit when a component's fraction is negative or collapsed to zero.</p>
            </div>
            <p><b>A non-monotonic normalized curve is not proof the transitions themselves aren't independent</b> &mdash; it's also exactly what genuinely independent transitions can look like at an unlucky choice of extraction wavelength, if their individual spectral contributions happen to have opposite signs there. <i>Worked example, from this app's own bundled 3-transition test dataset (all three transitions built as fully independent by construction, no real coupling at all):</i> extracting at 262 nm gives a good-looking R&sup2; (0.9999) but still a genuine negative fraction for one component (-0.13) &mdash; not a clean, fully physical decomposition, just a much milder version of the same problem; extracting at 300 nm instead gives a severely non-monotonic curve, a badly distorted fit, and a much worse R&sup2; (0.03). Neither wavelength gives a truly clean fit here &mdash; same underlying (fully independent) transitions, same molecule, only the DEGREE of the problem differs by extraction wavelength, not whether the problem exists at all. A single extracted curve can't distinguish "these transitions really do compete/convert into each other" from "these transitions are independent, but I picked a wavelength where they partly cancel" &mdash; both produce the same kind of non-monotonic shape. Extracting at a different wavelength, or (more rigorously) a full spectral decomposition method (NMF, MCR-ALS) working on the whole spectrum rather than one extracted wavelength, are the ways to actually tell these apart &mdash; this tool, built around a single extracted curve, structurally cannot.</p>

            <div class="screenshot">
                <img src="$NASTY_VS_CLEAN" width="$NASTY_VS_CLEAN_W" height="$NASTY_VS_CLEAN_H" alt="262 nm vs 300 nm comparison on the same independent transitions" />
                <p class="caption">Same fully-independent transitions, two extraction wavelengths — 262 nm (mild) vs. 300 nm (severe).</p>
            </div>
            <p>The "Low-T and High-T baselines cross" warning (see Normalization above) is a related but numerically distinct symptom with the same root cause, not the fitting problem itself. Normalization computes <code>A_corr(T) = (A(T) - A_low(T)) / (A_high(T) - A_low(T))</code>, where A_low(T) and A_high(T) are two straight, extrapolated lines evaluated across the WHOLE temperature range, not just their own home regions &mdash; think of them as a "floor" and "ceiling" defining what counts as 0 and what counts as 1. If those two lines happen to cross somewhere in the middle (both being straight-line extrapolations, not the real flat asymptotes the curve may actually have), the "distance between floor and ceiling" briefly becomes zero right there — and dividing by (nearly) zero makes the normalized value swing to huge, meaningless numbers near that point, regardless of what the real signal is doing. A large enough reversal in the raw curve makes this baseline-crossing more likely (the straight-line guess is more likely to misjudge where the true baselines are), which is why the two tend to show up together — but they're still two distinct problems: one about which SHAPE this tool's model can represent (this section), the other about the ARITHMETIC of turning raw signal into a 0-1 scale (Normalization, above).</p>
            <p><b>Important correction, verified directly rather than assumed:</b> a negative fraction is <i>not</i> reliable evidence of non-independence even by itself, and can appear on curves that look perfectly well-behaved (mild, near-monotonic, at a "good" extraction wavelength). The reason is a small, unavoidable mismatch between this tool's fitted shape and the true two-state model, present in essentially every 3+-component fit to some degree, independence notwithstanding &mdash; explained fully next.</p>
            <p><b>"Extract at an isosbestic point and you'll get a terrible fit" is not a safe rule either &mdash; verified by scanning every 5 nm from 210 to 390 nm on the same bundled 3-transition dataset.</b> This dataset has three isosbestic points, one per transition (235, 290, 345 nm &mdash; see the Info sheet of the bundled workbook). Extracting exactly at each one gives three very different results: 235&nbsp;nm &rarr; R&sup2;&nbsp;=&nbsp;1.0000 (excellent), 290&nbsp;nm &rarr; R&sup2;&nbsp;=&nbsp;&minus;0.01 (genuinely terrible &mdash; worse than just fitting a flat line), 345&nbsp;nm &rarr; R&sup2;&nbsp;=&nbsp;0.9995 (excellent). Sitting at <i>a</i> transition's own isosbestic point only removes THAT transition's contribution there &mdash; whether the fit then succeeds or fails depends entirely on whether the <i>remaining</i> transitions' contributions happen to still add up same-signed (235 nm, 345 nm) or partly cancel (290 nm), exactly the same same-sign criterion described above. The genuinely bad stretches found by the full scan &mdash; roughly 220&ndash;230, 285&ndash;305, and 355&ndash;370 nm &mdash; sit <i>near</i> but not exactly centered on the isosbestic points, and differ a lot in width and severity (285&ndash;305 nm is by far the widest and worst of the three).</p>
            <p><b>But a high R&sup2; at an isosbestic point is itself a trap, not a reassurance &mdash; because the transition that's isosbestic there has been silently removed from the data, not fitted well.</b> Verified directly: at 235&nbsp;nm (transition 1's own isosbestic point, true Tm&nbsp;=&nbsp;30&deg;C), even a single sigmoid alone already reaches R&sup2;&nbsp;=&nbsp;0.9995 &mdash; barely below the 3-component fit's 1.0000 &mdash; because transition 1 contributes essentially nothing there, leaving a curve that's really only 2 transitions wide. Look at where the 3-component fit's own midpoints land: 69.4, 54.8, 76.0&deg;C &mdash; none anywhere near transition 1's real 30&deg;C. The "3rd component" isn't recovering transition 1 at all; it's splitting transitions 2 and 3 (true Tm&nbsp;55&deg;C and 78&deg;C) into three pieces to soak up 3 components' worth of fitting freedom on a curve that only has 2 real degrees of freedom. The same thing happens at 345&nbsp;nm (transition 3's own isosbestic point, true Tm&nbsp;=&nbsp;78&deg;C): 3-component midpoints of 61.4, 48.4, 54.9&deg;C, nowhere near 78&deg;C. Only at 262&nbsp;nm &mdash; where all three transitions genuinely contribute &mdash; do the fitted midpoints land on the true values: 30.3, 55.0, 77.6&deg;C, matching 30/55/78&deg;C almost exactly. So an excellent-looking fit at an isosbestic point isn't a sign you picked a safe wavelength; it can mean the opposite &mdash; one real transition's variability has been cut out of the data entirely, and the reported Tm/&Delta;H/&Delta;S for whichever component "represents" it are not measuring that transition at all, just however the fit happened to redistribute the remaining two among three slots.</p>
            <p>This is the real reason a full spectral decomposition (NMF, MCR-ALS, SVD) is preferable to any single extracted wavelength, isosbestic or not: it's not just about dodging unpredictable bad R&sup2; bands (previous paragraph) &mdash; it's that using every wavelength at once means no single transition's variability can be silently zeroed out the way it structurally is at that transition's own isosbestic point. A single extracted curve, however carefully the wavelength is chosen, can only ever see as many transitions as happen to have nonzero signal at that one point; a full spectral method sees all of them, everywhere, simultaneously.</p>

            <table class="data-table">
                <tr>
                    <th>Extraction X</th>
                    <th>What's there</th>
                    <th>R&sup2; (3-comp. fit)</th>
                    <th>Fitted midpoints (&deg;C)</th>
                    <th>True Tm (&deg;C): 30, 55, 78</th>
                </tr>
                <tr>
                    <td>235 nm</td>
                    <td>T1's own isosbestic point</td>
                    <td class="num">1.0000</td>
                    <td>54.8, 69.4, 76.0</td>
                    <td>T1 (30&deg;C) invisible &mdash; the other two are split across 3 slots instead</td>
                </tr>
                <tr>
                    <td>262 nm</td>
                    <td>Recommended extraction X</td>
                    <td class="num">0.9999</td>
                    <td>30.3, 55.0, 77.6</td>
                    <td>All three genuinely visible &mdash; midpoints match to within &plusmn;0.4&deg;C</td>
                </tr>
                <tr>
                    <td>290 nm</td>
                    <td>T2's own isosbestic point</td>
                    <td class="num">&minus;0.01</td>
                    <td>fit collapses (factors pinned at &plusmn;1)</td>
                    <td>Remaining transitions partly cancel &mdash; not just one missing, the fit fails outright</td>
                </tr>
                <tr>
                    <td>345 nm</td>
                    <td>T3's own isosbestic point</td>
                    <td class="num">0.9995</td>
                    <td>48.4, 54.9, 61.4</td>
                    <td>T3 (78&deg;C) invisible &mdash; the other two are split across 3 slots instead</td>
                </tr>
            </table>
            <p style="font-size:0.9em; color:#7f8c8d;">Same bundled 3-transition dataset, same baselines (Low-T [5.0, 18.5]&deg;C / High-T [81.5, 95.0]&deg;C) and 3-component unconstrained Logistic fit throughout &mdash; only the extraction wavelength changes between rows. Note that R&sup2; alone doesn't distinguish the 235/345 nm rows from the 262 nm row &mdash; all three look "excellent" by that number alone; only the midpoints reveal that two of the four cases silently dropped a real transition.</p>

            <p>The same pattern holds across the full wavelength range, not just at these four points &mdash; scanning every 5 nm from 210 to 390 nm shows the bad stretches sitting <i>near</i> the isosbestic points without being centered on them, and shows the isosbestic points themselves (235, 345 nm) sitting well inside broad, otherwise-excellent-looking plateaus:</p>

            <div class="screenshot">
                <img src="$R2_SCAN" width="$R2_SCAN_W" height="$R2_SCAN_H" alt="R-squared vs extraction wavelength, full 210-390nm scan" />
                <p class="caption">3-component fit R&sup2; across the full scan. Isosbestic points (dashed gray) and the three genuinely bad stretches (shaded) don't line up exactly &mdash; and two of the three isosbestic points sit inside high-R&sup2; plateaus, which is exactly what makes them a trap rather than an obvious warning sign.</p>
            </div>
        </div>
        <div class="warning">
            <h4>Lessons learned: this is not a "3+ components" problem — it can happen with just 2</h4>
            <p>It's tempting to conclude, after running into a "nasty" (non-monotonic, wrong-sign) curve with 3 components, that the problem is specifically about having 3 or more of them. <b>That's not accurate.</b> Verified directly on this app's own bundled 2-transition test dataset (built the same way as the 3-transition one, from two independent transitions with a deliberately opposite-signed spectral contribution): scanning across wavelengths from 210 to 390 nm, the curve is genuinely non-monotonic (well over 50% of its range spent backtracking) at roughly half of the wavelengths tested &mdash; it just so happens that this dataset's own recommended default wavelength lands safely inside the one well-behaved stretch, so a user following that recommendation never runs into it. Try extracting the 2-transition dataset at, say, 220 nm or 350 nm instead of its recommended default, and the same non-monotonic, hard-to-fit behavior shows up with only 2 components.</p>
            <p>What actually determines whether a curve is nasty at a given wavelength is not the component count directly &mdash; it's whether the <i>transitions present have opposite-signed spectral contributions there</i> (see "This model assumes independent transitions" above for what that means precisely). With more transitions, there are simply more <i>pairs</i> of transitions that could end up opposite-signed at any given wavelength, so nasty regions tend to become more common and harder to avoid entirely as the number of real transitions in a sample grows &mdash; but this is a matter of it becoming statistically more likely with more components, not a hard rule that kicks in specifically at 3. A real sample's own isosbestic points (if it has genuine ones, and where they happen to sit) are what actually determines this for any specific molecule; this tool has no way to know that in advance; only exploration (or the full spectral methods below) can reveal it.</p>
            <p>The bundled 3-transition dataset happens to be the more thoroughly-explored example in this documentation only because its recommended wavelength, unlike the 2-transition dataset's, does not fall inside as forgiving a region &mdash; not because 3 components is inherently the threshold where this starts to matter.</p>
        </div>
        <div class="key-feature">
            <h4>When single-wavelength fitting keeps struggling: full-spectrum alternatives</h4>
            <p>If a curve looks nasty (or a fit keeps producing negative/collapsed fractions) at several different extraction wavelengths, not just one unlucky choice, that's a meaningful signal this tool's core assumption &mdash; picking one wavelength and treating whatever happens there as representative &mdash; may not suit this particular sample well. Methods that use the <i>whole</i> spectrum at once, evaluating every wavelength simultaneously rather than one at a time, are structurally able to answer questions this tool cannot: NMF, MCR-ALS, and SVD-based decomposition (if available elsewhere in this application) all work this way. They come with their own assumptions, limitations, and interpretive caveats &mdash; none of them is a drop-in replacement that "just works" where single-wavelength fitting struggles &mdash; but they are the more appropriate class of tool to reach for once single-wavelength extraction has shown itself to be wavelength-sensitive in this way, rather than trying more and more extraction wavelengths by hand.</p>
        </div>
        <div class="key-feature">
            <h4>Why even a well-behaved, independent transition doesn't fit perfectly — the T-linear vs. 1/T-linear mismatch</h4>
            <p>The true two-state (van't Hoff) model for one transition, as used above in Thermodynamic Parameters, is <code>K(T) = exp[(deltaH/R)(1/Tm - 1/T)]</code>, fraction = K/(1+K) &mdash; its natural variable is <b>1/T</b>. This tool's Sigmoid Fit instead uses <code>1/(1 + exp(-(T-Tm)/lambda))</code> &mdash; a shape whose natural variable is <b>T</b> directly. These are similar-looking S-curves, but not the same function of T. Near Tm, <code>1/T</code> is approximately linear in T (a first-order Taylor expansion: <code>1/T &asymp; 1/Tm - (T-Tm)/Tm&sup2;</code>), which is exactly why <code>lambda &asymp; R&middot;Tm&sup2;/deltaH</code> is a good local conversion between the two forms &mdash; but away from Tm, that linear approximation quietly breaks down, and the two curves diverge by a small amount.</p>
            <p>This is not a flaw specific to this tool &mdash; both parameterizations are standard, widely used, and this exact relationship between them is documented in the biophysics literature. Differential scanning fluorimetry / thermal shift assays commonly fit exactly this tool's T-linear form (often called a "Boltzmann sigmoidal equation" there) as a matter of routine &mdash; see <a href="#ref-niesen">Niesen, Berglund &amp; Vedadi (2007)</a>, one of the most widely used DSF protocol references. Separately, a paper on determining ligand dissociation constants from thermal shift data derives this same T-linear form directly as a small-temperature-range approximation of the van't Hoff equation, stating explicitly that it is valid "because the analysis is performed in a range of temperatures much smaller than the absolute temperatures," and confirms it matches the empirical Boltzmann form used elsewhere &mdash; see <a href="#ref-bhayani">Bhayani &amp; Ballicora (2022)</a>. This tool's own thermodynamic-parameters calculation above uses the rigorous 1/T-linear form directly (see <a href="#ref-mergny">Mergny &amp; Lacroix (2009)</a> at the bottom of this page); Sigmoid Fit's own shape parameter is the more common, T-linear approximation &mdash; consistent with standard practice, but not identical to it.</p>
            <p>Directly verified in this tool's own development: comparing an <i>exact</i> van't Hoff curve for a single, perfectly independent transition against its best-possible T-linear logistic approximation (zero noise, zero optimization involved — just the two mathematical forms, see <a href="#impl-shapemismatch">Implementation Details</a> for both) gives R&sup2; = 0.99997, not exactly 1.0. The mismatch is smallest right at Tm and grows further out in the wings. For a single component this residual is negligible. But for 3+ components, <code>curve_fit</code> has a genuine incentive to spend a little of a spare component's fraction on absorbing this systematic mismatch wherever it can, rather than leaving it as unexplained residual &mdash; and pushing that fraction slightly negative is one of the ways it can do that, even on data generated from fully independent transitions with no real coupling at all. One independent report specifically on biphasic (2-population) melting notes the T-linear ("Boltzmann") fit performing poorly compared to derivative-based methods for exactly this kind of multi-population case &mdash; see <a href="#ref-vivoli">Vivoli, Novak, Littlechild &amp; Harmer (2014)</a>, consistent with what's described here.</p>
        </div>
        <div class="tip">
            <p><b>Note for anyone who used earlier versions of this tool:</b> a "Fit fractions non-negative (compare R&sup2;)" checkbox used to live here — a second, constrained fit that forced every fraction to be non-negative, shown purely as an R&sup2; comparison next to the normal fit. It was removed after real-world testing showed the comparison could be actively misleading: the constrained fit doesn't necessarily keep the same physical transitions and simply make their fractions honest — it can just as easily abandon a real, well-resolved transition entirely and replace it with a spurious, overlapping split of a different one, while still landing on a similar-looking R&sup2;. A small R&sup2; gap between the two fits was never reliable evidence that the flagged component didn't matter. The underlying negative/collapsed-to-zero-fraction warning (above) is still the right signal to watch for; there's no substitute in this tool for the judgment call of checking whether a flagged component's midpoint still sits near where you'd otherwise expect a real transition.</p>
        </div>
        <div class="key-feature">
            <h4>Thermodynamic parameters (per component)</h4>
            <p>Click the collapsible <b>"&#9654; Thermodynamic parameters (per component)"</b> row (below the guesses/fit-results table) to reveal a table of each transition's own Tm, deltaH, deltaS, and deltaG &mdash; the same generalized per-component calculation the plot's per-component Arrhenius panels use (see below), shown as numbers instead of only on the plot. Like the guesses table above it, this updates live from whatever's currently shown there — a real Fit result, or a live preview of the current guesses/edits before one exists — not only after clicking Fit. deltaG = deltaH &minus; T&times;deltaS is evaluated at the <b>reference temperature</b> spinbox next to the toggle (default 37&deg;C, physiological temperature) &mdash; change it and the table updates immediately. Each row's text is colored to match that component's color on the plot, so it's easy to tell which row belongs to which transition at a glance.</p>

            <div class="screenshot">
                <img src="$THERMO_TABLE" width="$THERMO_TABLE_W" height="$THERMO_TABLE_H" alt="Per-component thermodynamics table, expanded" />
                <p class="caption">The per-component thermodynamics table, expanded — row colors match the plot below.</p>
            </div>
        </div>
        <div class="key-feature">
            <h4>Per-component Arrhenius plots</h4>
            <p>With <b>"Show component fits &amp; Arrhenius plots"</b> checked (default), a successful fit adds one row per transition below the main plots: on the left, that component's own isolated curve &mdash; the real data with every OTHER component's contribution removed and renormalized back to a standalone 0&ndash;1 transition, alongside its ideal fitted model curve and a dotted line at its own Tm; on the right, that component's own Arrhenius plot and linear fit. This is the direct generalization of the single Arrhenius approach above to multiphasic curves: <i>"the calculation of thermodynamic parameters of multiple transitions is just a generalization of the calculation for single transitions"</i>, applied to each decomposed component in turn.</p>

            <div class="screenshot">
                <img src="$PLOT_PANELS" width="$PLOT_PANELS_W" height="$PLOT_PANELS_H" alt="Full plot panel stack for a completed fit" />
                <p class="caption">The full plot stack: Original/Normalized curves, residual, and per-component panels.</p>
            </div>

            <p>Importantly, this Arrhenius fit runs on the same real reconstructed data shown as gray points in the plot &mdash; not on the component's theoretical model curve. Using the theoretical curve would make it circular (an Arrhenius fit on a mathematically perfect sigmoid just recovers that same sigmoid's own midpoint back, telling you nothing new); using the real data makes this a genuine, independent check of whether that transition's actual behavior is consistent with simple two-state thermodynamics &mdash; for a single-component fit this reconstruction reduces exactly to the original measured data itself (there's no other component's contribution to remove), so this per-component result IS the whole-curve Arrhenius calculation, not merely similar to it (see the note above this section for why the tool no longer shows that as a separate control); for a genuine multi-transition curve the per-component results will typically differ from what a naive whole-curve calculation would have given, and the standard errors will be larger than a theoretical-curve fit would ever show, since real data has real scatter. (For the exact reconstruction formula, see <a href="#impl-reconstruction">Implementation Details</a>.)</p>
            <p>For heavily overlapping components, this reconstruction inherits some of the whole fit's residual (whatever the model didn't explain, with no independent identity attributable to one component over another) into whichever component is currently being isolated. This isn't an approximation or a compromise &mdash; it's the only principled way to handle it: from that component's own perspective, "everything left over once the other components' predicted contributions are removed" genuinely is its isolated signal, imperfections included.</p>
            <p>Note that a component's own dH/dS, especially for closely-spaced or heavily overlapping transitions, is intrinsically an approximation &mdash; the empirical T-linear sigmoid shape this fit uses to locate transitions doesn't transform exactly into the 1/T-linear form the Arrhenius calculation assumes (the same caveat the original approach's own findings note). Tm is generally recovered much more reliably than deltaH/deltaS.</p>
        </div>
        <div class="key-feature">
            <h4>Fit Details (next to Fit, top of this group)</h4>
            <p>One compact dropdown button instead of several separate ones, to keep that row from getting crowded — click it for <b>Show...</b> (preview the report in its own small window, with its own Copy/Save buttons), <b>Copy to Clipboard</b>, or <b>Save to File...</b>. All three produce the same full plain-text report of the current fit &mdash; curve/extraction/normalization settings, each component's fraction/midpoint/width (with standard errors where available) and (if computed) deltaH/deltaS/Tm, and the overall fit quality (R&sup2;, RMSD). Requires a fit (real or preview — see "The guesses table" above) to exist first.</p>
        </div>

        <h3>Output Options (Adds New Spectra)</h3>

        <div class="screenshot">
            <img src="$OUTPUT_OPTIONS" width="$OUTPUT_OPTIONS_W" height="$OUTPUT_OPTIONS_H" alt="Output Options group" />
            <p class="caption">Output Options: nothing is saved unless at least one of these is checked.</p>
        </div>

        <p>These are all optional and <b>unchecked by default</b> — this dialog's main purpose is the analysis itself (the numbers and fit), not necessarily saving new spectra every time; plenty of workflows just want to inspect a fit and close without adding anything to the main list. When checked, they <b>add</b> new spectra (temperature on the x-axis) to your main list. The source spectra are never modified. Click the &#9660;/&#9654; toggle at the top of this group to show/hide the checkboxes — collapsed by default, matching Saved Fits' same default state.</p>
        <ul>
            <li><b>Add extracted (raw) curve:</b> the unmodified extracted (temperature, signal) curve.</li>
            <li><b>Add normalized curve:</b> the 0&ndash;1 normalized curve.</li>
            <li><b>Add low/high-T baseline curves:</b> the two fitted baseline lines, each as its own spectrum.</li>
            <li><b>Add total fit curve:</b> the summed sigmoid-fit curve.</li>
            <li><b>Add residual:</b> (normalized or raw curve) minus the total fit.</li>
            <li><b>Add individual transition components:</b> each fitted sigmoid component as its own spectrum, named <code>&lt;curve name&gt;_component_01</code>, <code>_component_02</code>, etc.</li>
        </ul>

        <div class="key-feature" id="ok-behavior">
            <h3>What Happens When You Click OK?</h3>
            <p><b>Nothing is saved unless you check at least one Output Option.</b> Building and fitting a melting curve is treated as analysis, not a change to the source spectra &mdash; their data and metadata are never touched by this dialog alone. This applies to the one curve you're currently working on &mdash; <b>Saved Fits entries are never turned into spectra</b> just by being saved; that container is purely for keeping results around to compare, independent of OK/Output Options.</p>
            <ol>
                <li><b>If no Output Options are checked:</b> the analysis is discarded once you close the dialog. Nothing is added to the spectrum list and this doesn't appear in Operations History.</li>
                <li><b>If any Output Options are checked:</b> the corresponding new spectra are created and added to your main list, each carrying its own metadata describing exactly how it was produced (source spectra, temperatures, fit parameters), viewable via that spectrum's own Metadata panel.</li>
            </ol>
            <p>Either way, that run also gets an entry in <b>Operations History</b> whenever it appears there at all. Its <b>Parameters</b> view (right-click &rarr; View Parameters, or the equivalent from wherever Operations History is shown) lists the human settings directly — source spectra, extraction/normalization settings, fit settings, which Output Options were checked — with the heavy computed results (the curve itself, the fit, per-component thermodynamics) collapsed behind one <b>"Fit &amp; Curve Detail"</b> row instead of dumped as raw numbers; click it for a readable breakdown, including the full per-temperature table. For a multi-transition fit, that table also gets one <b>"Data (reconstructed)"</b> and one <b>"Model"</b> column per component — the same real isolated data and ideal fitted curve shown on the plot itself (see "Per-component Arrhenius plots" above for exactly what each one is); the dialog's own small <b>"?"</b> button next to Close gives the short version without leaving it.</p>
        </div>

        <div class="tip">
            <strong>Pro Tip:</strong> If the sigmoid fit fails to converge with more than one component, click <b>Auto-detect Transitions</b> first &mdash; the fit is much more reliable with midpoint guesses that are already close to the real transitions.
        </div>

        <h2>Implementation Details</h2>
        <p style="font-style: italic; color: #7f8c8d;">The exact formulas behind the calculations described above, collected here rather than inline, since most users won't need them day to day. Each is linked from the relevant section above ("see Implementation Details").</p>

        <h3><a name="impl-normalization"></a>Baseline normalization</h3>
        <p>Low-T and High-T baseline regions are each fit independently (constant or linear least-squares) to get <code>A_low(T)</code> and <code>A_high(T)</code>, extrapolated across the WHOLE temperature range. Then:</p>
        <p style="text-align:center;"><code>A_corr(T) = (A(T) - A_low(T)) / (A_high(T) - A_low(T))</code></p>
        <p>always running 0-to-1 low-to-high-T regardless of which way the raw signal moved. See "Low-T and High-T baselines cross" above for what happens when <code>A_high(T) - A_low(T)</code> passes through zero.</p>

        <h3><a name="impl-xtrans"></a>X_trans (median-crossing temperature)</h3>
        <p>The temperature where the RAW (not normalized, not fitted) curve directly crosses the median line <code>(A_low(T) + A_high(T)) / 2</code>, found by linear interpolation between the two data points that bracket the sign change. Purely geometric — no regression, no threshold-based point filtering, involved at all, which is why it's independent of Threshold (span) and generally differs slightly from the Arrhenius-derived Tm.</p>

        <h3><a name="impl-arrhenius"></a>Arrhenius / van't Hoff transform</h3>
        <p>For a two-state equilibrium, define <code>K(T) = A_corr(T) / (1 - A_corr(T))</code> (the equilibrium constant implied by the normalized signal), restricted to the Threshold span. The van't Hoff equation:</p>
        <p style="text-align:center;"><code>ln(K) = -deltaH/R &times; (1/T) + deltaS/R</code></p>
        <p>is linear in <b>1/T</b> (not T) &mdash; deltaH from the slope, deltaS from the intercept (R = 8.314 J/mol/K), by ordinary least-squares linear regression on the threshold-filtered points. Tm is where the fitted line crosses ln(K) = 0. With 3+ points, standard errors on deltaH and deltaS come directly from the regression's own slope/intercept standard errors (via <code>scipy.stats.linregress</code>).</p>
        <p><b>Tm's error is not simply the intercept error divided through &mdash; it requires the slope/intercept covariance.</b> Tm corresponds to <code>x&#8320; = -intercept/slope</code> (in 1/T), a nonlinear combination of both regression coefficients. Propagating its uncertainty via the delta method needs <code>Var(slope)</code>, <code>Var(intercept)</code>, <i>and</i> <code>Cov(slope, intercept)</code> &mdash; and for ordinary least squares this covariance is <b>not zero</b> whenever the x-data isn't centered near zero, which 1/T (in Kelvin) never is. It has the closed form <code>Cov(slope, intercept) = -mean(x) &times; Var(slope)</code>, computed directly rather than requiring a separate covariance-matrix fit. Treating slope and intercept as independent (dropping this covariance term) systematically <b>inflates the reported Tm error, often by an order of magnitude or more</b> &mdash; verified by Monte Carlo simulation (repeated noisy resampling of a synthetic Arrhenius plot): the true spread in the recovered Tm was &asymp;1&deg;C, the independence-assumption formula reported &asymp;67&deg;C, and the covariance-aware formula below reported &asymp;1.6&deg;C, matching the Monte Carlo result to the right order of magnitude. The full delta-method formula actually used:</p>
        <p style="text-align:center;"><code>Var(x&#8320;) = Var(intercept)/slope&sup2; + (intercept&sup2;/slope&#8308;)&times;Var(slope) &minus; (2&times;intercept/slope&sup3;)&times;Cov(slope,intercept)</code></p>
        <p>with Tm's standard error obtained by propagating <code>sqrt(Var(x&#8320;))</code> from 1/T back through to degrees C.</p>

        <h3><a name="impl-reconstruction"></a>Per-component data reconstruction</h3>
        <p>For a multi-component fit, each component's own Arrhenius analysis (used in the per-component thermodynamics table and per-component Arrhenius plots) needs that component's own isolated curve &mdash; not the whole measured curve, and not a purely theoretical model curve (see "Per-component Arrhenius plots" above for why not the latter, and why real-data reconstruction is the scientifically sound choice here rather than a simplification). For component <i>i</i> out of N, with measured data <code>y_measured</code>, the whole fit's own total curve <code>y_fit_total</code> (the sum of every component), and that component's own fitted scale factor <code>factor<sub>i</sub></code>:</p>
        <p style="text-align:center;"><code>y_local_data(i) = [y_measured &minus; (y_fit_total &minus; factor<sub>i</sub> &times; shape<sub>i</sub>(T))] / factor<sub>i</sub></code></p>
        <p>i.e. subtract every OTHER component's fitted contribution from the real measured curve (equivalently: remove the whole fit's residual-free prediction, then add this component's own theoretical shape back in), then divide by this component's own factor to rescale the result back to a full 0-1 span. Algebraically this simplifies to <code>[y_measured - sum of every OTHER component's fitted contribution] / factor<sub>i</sub></code> &mdash; the residual (whatever the whole fit didn't explain) ends up folded entirely into whichever component is currently being isolated, which is the correct, principled way to handle it (see "Per-component Arrhenius plots" above).</p>
        <p><b>Why N=1 always reduces to y_measured exactly</b> (not approximately &mdash; this is why the removed whole-curve calculation and Sigmoid Fit's own per-component result were always provably identical for a single component, not merely similar): with one component, its own factor is always exactly 1 (not fitted &mdash; a direct algebraic consequence of there being only one component to split 100% between), and the whole fit's total curve <code>y_fit_total</code> is then just <code>1 &times; shape<sub>1</sub>(T)</code>, i.e. exactly <code>shape<sub>1</sub>(T)</code> itself. Substituting both into the formula above:</p>
        <p style="text-align:center;"><code>y_local_data(1) = [y_measured &minus; (shape<sub>1</sub>(T) &minus; 1 &times; shape<sub>1</sub>(T))] / 1 = [y_measured &minus; 0] / 1 = y_measured</code></p>
        <p>The <code>shape<sub>1</sub>(T)</code> terms cancel to exactly zero regardless of what midpoint or width the sigmoid fit actually converged to &mdash; a fit with a poor starting guess and a fit with a perfect one both still reduce to this same identity, since the cancellation happens before either value ever gets used. The two calculations were never independently arriving at the same answer through different reasoning; the per-component formula becomes, by the algebra alone, a direct restatement of the whole-curve one the moment there's only one component to isolate.</p>
        <p>Worth being precise about: the two computational <i>paths</i> genuinely differ — Sigmoid Fit solves a nonlinear least-squares problem (searching for the best midpoint and width) that the removed whole-curve calculation never did at all. But that nonlinear step's own output is exactly what cancels out of the formula above, before the Arrhenius regression runs on whatever remains. So the extra work happens, then gets discarded for this particular number — not two methods coincidentally landing on the same answer, but one method doing strictly more work than needed to produce it. That "more work" isn't wasted, though: it's also what makes the sigmoid's own midpoint/width (and their standard errors, in the fit results table) available at all, which the removed whole-curve calculation had no way to provide, since it never fit a shape in the first place. That's the real reason Sigmoid Fit was kept over the other one — not merely equivalent, but strictly more informative for the one case where both were ever available.</p>

        <h3><a name="impl-shapemismatch"></a>T-linear sigmoid vs. 1/T-linear van't Hoff</h3>
        <p>Sigmoid Fit's own shape is <code>1 / (1 + exp(-(T - Tm)/lambda))</code> &mdash; linear in T. The true van't Hoff two-state fraction, derived from the equation above, is <code>1 / (1 + exp((deltaH/R)(1/T - 1/Tm)))</code> &mdash; linear in 1/T. Near Tm, a first-order Taylor expansion (<code>1/T &asymp; 1/Tm - (T-Tm)/Tm&sup2;</code>) makes these approximately equal, with <code>lambda &asymp; R &times; Tm&sup2; / deltaH</code> as the local conversion between them (the same relationship used in both directions elsewhere in this tool) &mdash; but the approximation is only local, and the two curves diverge further from Tm. See "Why even a well-behaved, independent transition doesn't fit perfectly" above for the numerical size of this gap and its consequences for 3+-component fits.</p>

        <h2>References</h2>
        <p>The linear-baseline normalization and Arrhenius/van't Hoff approach this tool implements follows the methodology described in:</p>
        <p style="margin-left: 1.5em;">
            <a name="ref-mergny"></a>Mergny, J.-L. and Lacroix, L. <i>UV Melting of G-Quadruplexes.</i><br/>
            <i>Current Protocols in Nucleic Acid Chemistry</i>, 17.1.1&ndash;17.1.15 (June 2009).<br/>
            DOI: <a href="https://doi.org/10.1002/0471142700.nc1701s37">10.1002/0471142700.nc1701s37</a><br/>
            PubMed: <a href="https://pubmed.ncbi.nlm.nih.gov/19488970/">https://pubmed.ncbi.nlm.nih.gov/19488970/</a>
        </p>
        <p>The T-linear ("Boltzmann sigmoid") vs. 1/T-linear (van't Hoff) shape mismatch discussed above (Sigmoid Fit) is documented in:</p>
        <p style="margin-left: 1.5em;">
            <a name="ref-niesen"></a>Niesen, F.H., Berglund, H. and Vedadi, M. <i>The use of differential scanning fluorimetry to detect ligand interactions that promote protein stability.</i><br/>
            <i>Nature Protocols</i> 2, 2212&ndash;2221 (2007).<br/>
            DOI: <a href="https://doi.org/10.1038/nprot.2007.321">10.1038/nprot.2007.321</a><br/>
            PubMed: <a href="https://pubmed.ncbi.nlm.nih.gov/17853878/">https://pubmed.ncbi.nlm.nih.gov/17853878/</a>
        </p>
        <p style="margin-left: 1.5em;">
            <a name="ref-bhayani"></a>Bhayani, J.A. and Ballicora, M.A. <i>Determination of dissociation constants of protein ligands by thermal shift assay.</i><br/>
            <i>Biochemical and Biophysical Research Communications</i> 590, 1&ndash;6 (2022).<br/>
            DOI: <a href="https://doi.org/10.1016/j.bbrc.2021.12.041">10.1016/j.bbrc.2021.12.041</a>
        </p>
        <p style="margin-left: 1.5em;">
            <a name="ref-vivoli"></a>Vivoli, M., Novak, H.R., Littlechild, J.A. and Harmer, N.J. <i>Determination of Protein-ligand Interactions Using Differential Scanning Fluorimetry.</i><br/>
            <i>Journal of Visualized Experiments</i> (91), e51809 (2014).<br/>
            DOI: <a href="https://doi.org/10.3791/51809">10.3791/51809</a><br/>
            PubMed: <a href="https://pubmed.ncbi.nlm.nih.gov/25285605/">https://pubmed.ncbi.nlm.nih.gov/25285605/</a>
        </p>
    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    the temperature table's Spectrum column.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body>
    </html>
    """)

    return help_template.safe_substitute(images)
