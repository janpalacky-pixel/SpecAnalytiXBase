# src/help/normalization_help.py

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path

# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build — same mechanism as
# interactive_subtraction_help.py / xaxis_alignment_help.py; see either for
# the full rationale. $KEY below resolves to a COMPLETE <img> tag (or a
# "not yet added" placeholder <div>) and is used bare in the template — no
# wrapping <img src="$KEY"> — since that double-wrapping is exactly what
# broke interactive_subtraction_help.py the first time around.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "normalization")

_SCREENSHOT_FILES = {
    "OVERVIEW": "dialog_overview.png",
    "REGIONS":  "regions_controls.png",
    "METHOD":   "method_tabs.png",
    "COMMIT":   "commit_buttons.png",
    "SCALING":  "result_scaling.png",
    "PREVIEW":  "preview_tab.png",
    "FACTORS":  "per_spectrum_factors.png",
    "PRESETS":  "region_presets.png",
}

_SCREENSHOT_ALT = {
    "OVERVIEW": "Normalization dialog overview",
    "REGIONS":  "Normalization region(s): Include/Exclude toggle with a quick-help \"?\" button, region list, From/To fields with Full range on the same row, Add region (relabeled Update when a region is selected, with a Cancel edit button appearing right next to it)/Remove buttons, then a separator before the Preset row",
    "METHOD":   "Normalization method group: Intensity and Scatter correction tabs with method radio buttons and formulas",
    "COMMIT":   "Help, Apply, Add as New, and Close buttons",
    "SCALING":  "Result scaling group: Standard, Keep original scale, and Custom target radio buttons",
    "PREVIEW":  "Raw and Preview (normalized) tabs with toolbar, Show shaded regions checkbox, hint text, plot, and Save selected spectra button",
    "FACTORS":  "Per-spectrum factors table with Spectrum, Factor, and Deviation (sigma from the mean, shown for every row) columns",
    "PRESETS":  "Region preset row: dropdown with Load, Save as, Delete, and help buttons",
}

# Cap displayed screenshot width at this many pixels — see
# interactive_subtraction_help.py's _MAX_IMG_WIDTH for the full explanation
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
    resolution. Screenshots not added yet fall back to a fixed-size
    placeholder box instead of a broken image icon."""
    values = {}
    for key, filename in _SCREENSHOT_FILES.items():
        abs_path = resource_path(os.path.join(_SCREENSHOT_DIR, filename))
        if not os.path.isfile(abs_path):
            values[key] = (
                '<div style="display:inline-block; width:400px; height:180px; '
                'background:#F4F5F7; border:1px dashed #B0B8C8; border-radius:6px; '
                'text-align:center; color:#7f8c8d; font-size:0.9em; padding-top:80px;">'
                f'screenshot not yet added ({filename})</div>'
            )
            continue
        uri = Path(abs_path).as_uri()
        try:
            native_w, native_h = _png_size(abs_path)
            display_w = min(native_w, _MAX_IMG_WIDTH)
            display_h = round(native_h * (display_w / native_w))
        except (OSError, ValueError):
            display_w, display_h = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)
        alt = _SCREENSHOT_ALT.get(key, filename)
        values[key] = (
            f'<img src="{uri}" width="{display_w}" height="{display_h}" '
            f'alt="{alt}" style="border-radius:6px; border:1px solid #dee2e6;" />'
        )
    return values


def get_normalization_help_title():
    return 'Normalization — help'


def get_normalization_help_content():
    images = _resolve_screenshot_uris()
    help_template = Template("""
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            h4    { color: #4A148C; margin-top: 12px; margin-bottom: 2px; }
            .cat  { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .detail { background: #FAFAFA; border-left: 4px solid #E65100;
                      padding: 10px 14px; margin: 6px 0 14px 0; border-radius: 3px; }
            .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note { background: #E3F2FD; border-left: 4px solid #1565C0;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn { background: #FFF8E1; border-left: 4px solid #F9A825;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm   { font-family: monospace; background: #ececec;
                    padding: 1px 5px; border-radius: 3px; }
            .det-link { font-size: 11px; color: #1565C0; }
            .back-link { font-size: 11px; color: #888; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>
    <a name="top"></a>

    <h1>Normalization</h1>

    <p>Normalization removes <em>systematic intensity differences</em> between spectra while
    preserving meaningful information (peak positions, relative intensities, band shapes).
    It does <strong>not</strong> remove baseline curvature — use the <em>Baseline Correction</em>
    step for that.</p>

    <div class="screenshot">
        $OVERVIEW
        <p class="caption">The full dialog: Selected spectra / Normalization method / Normalization region(s) on the left, Raw / Preview (normalized) tabs with the plot on the right.</p>
    </div>

    <h2>Workflow</h2>
    <ol>
        <li><strong>Define normalization region(s)</strong> — drag on the plot or enter
            From / To manually, then click <em>Add region</em>.
            Multiple regions are combined as a union (Include mode) or subtracted from
            the full range (Exclude mode). This section is expanded by default. Save
            frequently-used region sets as <a href="#presets">presets</a> for reuse.</li>
        <li><strong>Choose a method</strong> — pick from the Intensity or Scatter correction tabs.</li>
        <li><strong>Choose result scaling</strong> (Intensity methods only) — see
            <a href="#scaling">Result scaling</a> below.</li>
        <li><strong>Check the Preview tab</strong> — switch from Raw to Preview (normalized)
            to see the live result before committing. The preview updates automatically
            as settings change. Expand <a href="#factors">Per-spectrum factors</a> to
            check for outliers.</li>
        <li><strong>Click Apply or Add as New</strong> — Apply replaces the spectra loaded
            in the dialog with their normalized result; Add as New leaves the originals
            untouched and adds the result to the spectra list under new names instead.
            Both commit immediately, with their own confirmation and result message shown
            right in the dialog — there is no separate Run step in the main window for
            this operation.</li>
    </ol>

    <div class="screenshot">
        $REGIONS
        <p class="caption">Normalization region(s) — Include regions / Exclude regions toggle with a small round "?" quick-help button next to it, the region list, From / To fields (with Full range on the same row) and, below, Add region (becomes Update when editing) with Cancel edit right next to it, and Remove. A thin separator then divides these region controls from the Preset row below.</p>
    </div>

    <div class="tip">
        <strong>Editing an existing region:</strong> click a region in the list to select
        it — its From / To values load into the fields above, the
        <span class="fm">Add region</span> button relabels itself
        <span class="fm">Update</span>, and a <span class="fm">Cancel edit</span>
        button appears right next to it. Change the values and click
        <span class="fm">Update</span> to update that region in place instead of
        adding a new one; the row stays selected afterwards so you can keep adjusting it.
        Click <span class="fm">Cancel edit</span> to leave the region unchanged and go back
        to adding a new one (clicking empty space in the list does <em>not</em> deselect
        it — use the Cancel edit button). Updating (or adding) a region to values that
        exactly match another region already in the list is not allowed — that existing
        region is selected instead of creating a duplicate.
        <span class="fm">Remove</span> deletes the selected region(s) — Ctrl/Shift-click
        several regions in the list first to remove more than one at a time.
    </div>

    <div class="screenshot">
        $METHOD
        <p class="caption">Normalization method — Intensity / Scatter correction tabs, each method as a radio button with its formula, and the orange "? Method info" button below.</p>
    </div>

    <div class="tip">
        <strong>Apply vs. Add as New vs. Close:</strong>
        <ul>
            <li><strong>Apply</strong> replaces the spectra loaded in the dialog with their
                normalized result. The originals are overwritten once Apply runs.</li>
            <li><strong>Add as New</strong> leaves the originals completely untouched and
                adds the normalized result to the spectra list under new, unique names
                (e.g. <span class="fm">samplename_normalized</span>, with a number appended
                if that name is already taken).</li>
            <li><strong>Close</strong> closes the dialog without applying anything to the
                main window's spectra.</li>
        </ul>
        <p>Apply and Add as New close the dialog automatically once the commit succeeds. Whatever
        settings were last shown are still remembered the next time you reopen it for the same
        spectra, so it's easy to pick up where you left off — for example to try a different
        method or region and commit again.</p>
    </div>

    <div class="screenshot">
        $COMMIT
        <p class="caption">Help, Apply, Add as New, and Close, below the scrollable left panel.</p>
    </div>

    <div class="note">
        <strong>Which methods use the region?</strong> Every method except
        <strong>Reference spectrum</strong> uses the defined region to compute its result —
        including SVD and SNV, even though their formulas are batch- or statistics-based
        rather than a simple "I / factor". <strong>MSC</strong> has a checkbox
        ("Fit regression within region only") that controls this: unchecked (the
        default) fits its regression against the full spectrum regardless of any
        region; checked, it fits using only the defined region instead. Either way the
        correction is applied to the full spectrum. Reference spectrum is a point-wise
        division against another spectrum and never uses a region at all — there is no
        toggle for it. The Preview tab will not show a result until at least one region
        is defined (drag on the plot, or click "Full range" then "Add region"), except for Reference spectrum, and for
        MSC when its region checkbox is left unchecked — in both cases no region is
        actually needed, so requiring one would just be unnecessary friction.
    </div>

    <div class="note">
        <strong>Selected spectra (preview only):</strong> the collapsible "Selected spectra"
        section at the top lets you choose which spectra are <em>displayed</em> in the Raw
        and Preview tabs and which legend entries appear. This selection has no effect on
        the actual normalization — every spectrum loaded into the dialog is always
        normalized and included when computing "Keep original scale" averages, regardless
        of what is checked here. It is collapsed by default since it's usually set once.
    </div>

    <h2 id="scaling">Result scaling</h2>
    <p>Available for the five methods that divide by a single scalar factor
    (Peak intensity, Area, Vector norm, Robust peak, Mean of top N%). Not shown for
    Reference spectrum (a point-wise ratio, not a single factor) or for the Scatter
    correction methods (SNV, MSC, SVD), where a "target value" has no clean meaning.</p>
    <table>
        <tr><th>Option</th><th>Effect</th></tr>
        <tr>
            <td><strong>Standard</strong></td>
            <td>Each spectrum is divided by its own factor with no further scaling.
            For Peak intensity the result is exactly 1.0 at the maximum. For Area and
            Vector norm the result is <em>not</em> near 1.0 — it depends on your
            x-axis units and intensity scale. This is the default.</td>
        </tr>
        <tr>
            <td><strong>Keep original scale</strong></td>
            <td>Spectra are still corrected relative to each other, but the absolute
            scale stays close to the original data instead of being forced to 1.0.
            Example: if the per-spectrum factors are 100, 95, 105, the results become
            &asymp;1.00, &asymp;0.95, &asymp;1.05 &times; 100 &asymp; 100, 95, 105 &mdash;
            the same relative correction, but on the original scale. Useful when your
            data has a familiar magnitude (e.g. absorbance around 0.7, Raman counts
            around 10000) that you want preserved. The mean factor is always computed
            across <em>all</em> spectra loaded in the dialog, not just the ones currently
            shown in the Preview tab, so the result never depends on the preview
            selection.</td>
        </tr>
        <tr>
            <td><strong>Custom target</strong></td>
            <td>Multiplies the standard result by a value you specify, e.g. 0.7 or 10000.</td>
        </tr>
    </table>

    <div class="screenshot">
        $SCALING
        <p class="caption">Result scaling — Standard, Keep original scale, and Custom target (with its value spinbox), plus the orange "?" button that explains the three options.</p>
    </div>

    <h2>Live preview</h2>
    <p>The dialog has two tabs above the plot: <strong>Raw</strong> (the original spectra,
    used to define regions) and <strong>Preview (normalized)</strong> (the live result of
    applying the current method and result-scaling settings). The preview recomputes
    automatically — debounced by a short delay so rapid changes (typing, dragging a
    region) don't trigger a recompute on every keystroke. A brief wait cursor appears
    during the recompute; SVD and "Keep original scale" can take noticeably longer to
    preview on very large datasets, since both require processing every spectrum loaded
    in the dialog rather than only the previewed subset.</p>
    <p>The Preview tab shows nothing — just a message asking you to define a region —
    until at least one normalization region exists, for any method that actually needs
    one (see "Which methods use the region?" in the Workflow section above). This
    avoids showing what looks like a real result before you've actually configured
    anything. Click <strong>"Full range"</strong> in the Normalization region(s) section
    to fill the From/To fields with the entire spectrum, then click <strong>"Add
    region"</strong> to actually add it as a region — "Full range" only fills the
    fields, it does not add anything by itself, so it's safe to click even if you
    already have other regions defined.</p>
    <p>A <strong>Save selected spectra&hellip;</strong> button below the Preview plot exports
    the normalized result for whichever spectra are currently selected in the "Selected
    spectra" list, using the same Save dialog (text/Excel, table or individual files) as
    File &gt; Save in the main window. This lets you export a normalized result for
    inspection without needing to click Apply first.</p>

    <div class="screenshot">
        $PREVIEW
        <p class="caption">The Raw / Preview (normalized) tabs — toolbar with the Show shaded regions checkbox next to it, hint text, plot, and the Save selected spectra&hellip; button at the bottom of the Preview tab.</p>
    </div>

    <div class="tip">
        <strong>Show shaded regions:</strong> the Preview (normalized) tab shades the
        active normalization region(s) on its plot the same way the Raw tab does
        (green for Include mode, red for Exclude mode). A
        <span class="fm">Show shaded regions</span> checkbox next to the Preview tab's
        toolbar, checked by default, lets you hide that shading if it gets in the way
        of reading the normalized curves themselves.
    </div>

    <div class="note">
        <strong>Reference spectrum selection:</strong> the "Reference spectrum" dropdown
        (shown only for the Reference spectrum method) lists every spectrum loaded into
        the dialog by its actual label, numbered from 1 in loading order — not a plain
        index field. This removes any ambiguity about which spectrum "#3" refers to,
        especially after sorting the Selected spectra list, since the dropdown always
        shows the real name.
    </div>

    <h2 id="factors">Per-spectrum factors</h2>
    <p>A collapsible <strong>"Per-spectrum factors"</strong> section sits below the Preview
    plot, listing the raw computed factor for every spectrum before any result scaling
    is applied, plus how many standard deviations (&sigma;) that factor sits from the
    batch mean. Shown for the five Result-scaling-eligible methods (peak value, integrated
    area, vector norm, percentile, or top-mean) <strong>and for SVD factor normalization</strong>
    (the first-PC loading factor — see <a href="#det-svd">SVD algorithm details</a>).
    Hidden entirely for SNV, MSC, Reference spectrum, Offset correction, and Min-max,
    which have no single per-spectrum scalar factor: SNV computes a mean and standard
    deviation independently per spectrum (two numbers, not one shared batch factor); MSC
    fits a 2-parameter regression per spectrum; Reference spectrum is a point-wise ratio,
    not a scalar. Collapsed by default since it's a diagnostic aid, not something needed
    on every normalization.</p>

    <div class="warn">
        <strong>Deviation column and outlier highlighting:</strong> every row shows its
        factor's deviation from the batch mean, e.g. <span class="fm">+1.06&sigma;</span>
        or <span class="fm">&minus;1.84&sigma;</span>. Rows are additionally highlighted in
        orange when that deviation exceeds &plusmn;3&sigma; — the highlight is the "this one
        needs attention" signal, the number itself is shown for every spectrum regardless.
        This is most useful with "Keep original scale" or SVD factor normalization selected,
        since both depend on a factor computed across the whole batch — a single spectrum
        with an inflated factor (e.g. from a cosmic ray spike sitting inside the
        normalization region, or an outlier loading in SVD) can quietly skew every other
        spectrum's result. Investigate flagged spectra before trusting the normalization:
        check for cosmic rays, baseline problems, or a region that accidentally includes
        noise rather than signal.<br><br>
        The Deviation column shows <span class="fm">—</span> instead of a value only when
        no meaningful standard deviation can be computed at all: fewer than 3 spectra, or
        all factors identical. With very few spectra, note that the largest possible
        deviation for any single point is mathematically capped well under 3&sigma; (e.g.
        at most 2&sigma; with only 5 spectra) — so the 3&sigma; outlier highlight may never
        trigger on a small batch even if one spectrum's factor looks clearly off by eye.
        The number itself is still shown and worth checking visually in that case.
    </div>

    <div class="screenshot">
        $FACTORS
        <p class="caption">The collapsible Per-spectrum factors table (Preview tab) — Spectrum, Factor, and Deviation (σ from the mean, shown for every row) columns, with outlier rows highlighted in orange.</p>
    </div>

    <h2 id="presets">Region presets</h2>
    <p>The Normalization region(s) section includes a <strong>Preset</strong> row with a
    dropdown, three buttons, and a <strong>?</strong> button that opens a quick
    explanation in the dialog itself. The dropdown sits between the "Preset:" label and
    the Load button — it shows empty until at least one preset has been saved; it is not
    a separate text field, just a combobox with nothing in it yet.</p>
    <table>
        <tr><th>Button</th><th>Effect</th></tr>
        <tr><td><strong>Save as&hellip;</strong></td>
            <td>Saves the <em>currently defined regions</em> (the list above this row)
            under a name you type in a popup. This is how the dropdown gets its first
            entry — there is nothing to load or delete until you save at least one
            preset. Prompts before overwriting an existing name.</td></tr>
        <tr><td><strong>Load</strong></td>
            <td>Replaces the current region list with whichever preset is selected in
            the dropdown.</td></tr>
        <tr><td><strong>Delete</strong></td>
            <td>Removes the selected preset permanently (confirmation required).</td></tr>
    </table>

    <div class="screenshot">
        $PRESETS
        <p class="caption">The Preset row at the bottom of Normalization region(s) — dropdown, Load, Save as&hellip;, Delete, and the orange "?" button.</p>
    </div>

    <p>Typical order: define regions &rarr; <em>Save as&hellip;</em> &rarr; name it &rarr;
    later, pick it from the dropdown &rarr; <em>Load</em>.</p>
    <p>Presets are saved to a file in your user profile
    (<span class="fm">~/.specanalytixbase/normalization_region_presets.json</span>) so
    they persist across dialog sessions and application restarts — they are not tied to
    any single project or dataset. Useful for standard sample types you normalize
    repeatedly, e.g. a "CD silent region" preset for far-wavelength baseline zeroing, or
    a "Raman fingerprint area" preset for a specific spectral window.</p>

    <div class="note">
        <strong>Typical pipeline order:</strong>
        Data range &rarr; Baseline correction &rarr; Smoothing &rarr;
        <strong>Normalization</strong> &rarr; Peak fitting / PCA.
        Normalizing before baseline correction can amplify the baseline into your data.
    </div>

    <hr>
    <h2>Intensity normalization</h2>
    <p>Each method computes one scaling factor from the selected region(s) and divides the
    <em>entire</em> spectrum by it.</p>

    <!-- ---- Peak intensity ---- -->
    <div class="cat">
        <h3>Peak intensity &nbsp;<span class="fm">I / I<sub>max</sub>(region)</span></h3>
        <p>Divides by the maximum intensity in the selected region(s). Simplest and most
        intuitive — use when the tallest peak in your region is well-defined and reproducible.
        Sensitive to noise spikes; prefer <em>Robust peak</em> for noisy data.
        See <a href="#scaling">Result scaling</a> to change the default 1.0 target.</p>
        <a class="det-link" href="#det-peak">&#9660; algorithm details</a>
    </div>

    <!-- ---- Area ---- -->
    <div class="cat">
        <h3>Area (integral) &nbsp;<span class="fm">I / &int;I dx (region)</span></h3>
        <p>Divides by the integrated area under the curve in the selected region(s).
        Preserves spectral shape and all relative intensities perfectly.
        Ideal for quantitative composition analysis (band-ratio studies, polymer blends).
        The standard result is not near 1.0 here — see
        <a href="#scaling">Result scaling</a> for "Keep original scale" or a custom target.</p>
        <a class="det-link" href="#det-area">&#9660; algorithm details</a>
    </div>

    <!-- ---- Vector norm ---- -->
    <div class="cat">
        <h3>Vector norm (L2) &nbsp;<span class="fm">I / &Vert;I&Vert;<sub>2</sub> (region)</span></h3>
        <p>Divides by the Euclidean norm of the selected region(s). Robust general-purpose
        choice; uses all points equally, not just the maximum. Standard in chemometrics
        preprocessing pipelines. The standard result is not near 1.0 — see
        <a href="#scaling">Result scaling</a> if you want to preserve the original magnitude.</p>
        <a class="det-link" href="#det-vector">&#9660; algorithm details</a>
    </div>

    <!-- ---- Robust peak ---- -->
    <div class="cat">
        <h3>Robust peak (Nth pct.) &nbsp;<span class="fm">I / P<sub>N</sub>(region)</span></h3>
        <p>Divides by the Nth percentile of intensities in the selected region (default N&nbsp;=&nbsp;95).
        Less sensitive to noise spikes and cosmic rays than peak intensity.
        Adjust N in the dialog: lower values tolerate noisier data.
        See <a href="#scaling">Result scaling</a> to change the default 1.0 target.</p>
        <a class="det-link" href="#det-quantile">&#9660; algorithm details</a>
    </div>

    <!-- ---- Mean of top N% ---- -->
    <div class="cat">
        <h3>Mean of top N% &nbsp;<span class="fm">I / mean(I &ge; P<sub>N</sub>) (region)</span></h3>
        <p>Divides by the mean of all points at or above the Nth percentile in the region.
        Better than the plain percentile for broad or flat-topped bands — averages the actual
        peak-top pixels rather than picking one threshold value.
        See <a href="#scaling">Result scaling</a> to change the default 1.0 target.</p>
        <a class="det-link" href="#det-topmean">&#9660; algorithm details</a>
    </div>

    <!-- ---- Min-max [0, 1] ---- -->
    <div class="cat">
        <h3>Min-max [0, 1] &nbsp;<span class="fm">(I &minus; I<sub>min</sub>) / (I<sub>max</sub> &minus; I<sub>min</sub>) (region)</span></h3>
        <p>Rescales the spectrum so that the minimum of the selected region maps to&nbsp;0 and the
        maximum maps to&nbsp;1. The same linear shift and scale are applied to the <em>full</em>
        spectrum. Useful when you want to compare band <em>shapes</em> across spectra regardless
        of absolute intensity.</p>
        <p><strong>Note:</strong> this method is sensitive to baseline offsets because both the
        minimum and maximum of the region determine the scaling. Apply baseline correction first
        for best results. Unlike peak-intensity or area normalization, spectra with the same
        shape but different baselines will not overlay exactly.</p>
        <a class="det-link" href="#det-minmax">&#9660; algorithm details</a>
    </div>

    <!-- ---- Offset correction ---- -->
    <div class="cat">
        <h3>Offset correction &nbsp;<span class="fm">I &minus; mean(I) (region)</span></h3>
        <p>Subtracts the mean intensity of the selected region from the <em>entire</em> spectrum
        as a constant offset. Use a spectral region where the signal should be zero &mdash;
        for example 320&ndash;330&nbsp;nm in CD or absorption spectroscopy.</p>
        <p>This zeros the baseline without any scaling, so absolute intensity differences between
        spectra are preserved. It is the standard first step for CD and UV-Vis absorption datasets
        where the far-wavelength region is expected to be flat and signal-free.</p>
        <a class="det-link" href="#det-offset">&#9660; algorithm details</a>
    </div>

    <!-- ---- Reference spectrum ---- -->
    <div class="cat">
        <h3>Reference spectrum &nbsp;<span class="fm">I / I<sub>ref</sub> (point-wise)</span></h3>
        <p>Divides each spectrum point-wise by a chosen reference spectrum, picked from a
        dropdown listing every loaded spectrum by its actual label. Use for ratio
        spectroscopy — dividing by a blank, a solvent background, or an instrument
        response function. Both spectra must share the same x-axis grid. Result scaling
        does not apply to this method since it is a point-wise ratio, not a single-factor
        division.</p>
        <a class="det-link" href="#det-ref">&#9660; algorithm details</a>
    </div>

    <!-- ---- SVD ---- -->
    <div class="cat">
        <h3>SVD factor norm. &nbsp;<span class="fm">I / |V<sub>1</sub>|</span></h3>
        <p>Singular Value Decomposition — uses the first principal component loadings as
        normalization factors across the whole batch. Like the other Intensity methods
        above, this divides each spectrum by a single computed factor; the difference is
        that the factor comes from a batch-wide PCA decomposition rather than from each
        spectrum's own peak, area, or norm. Corrects the dominant systematic variation
        (drift, thickness gradients, photodegradation) across the dataset.
        Best for large homogeneous datasets (&gt;&nbsp;20 spectra). The selected region
        is used as a mask before decomposition, so it does affect the result — restrict
        it to a part of the spectrum you trust if some regions are noisier than others.
        Check the <a href="#factors">Per-spectrum factors</a> table afterwards to catch
        any spectrum whose loading is an outlier.</p>
        <a class="det-link" href="#det-svd">&#9660; algorithm details</a>
    </div>

    <hr>
    <h2>Scatter correction</h2>
    <p>These methods correct for physical light scattering caused by particle size, surface
    roughness, or sample turbidity by reshaping each spectrum (removing an additive offset
    and/or a multiplicative slope), not just dividing by a single number. Essential for
    diffuse-reflectance NIR and solid-sample Raman measurements.</p>

    <!-- ---- SNV ---- -->
    <div class="cat">
        <h3>Scatter corr. (SNV) &nbsp;<span class="fm">(I &minus; &mu;) / &sigma;</span></h3>
        <p>Standard Normal Variate — mean-centres and scales each spectrum by its standard
        deviation over the selected region(s). Removes multiplicative and additive scatter
        simultaneously, independently for each spectrum. Standard for diffuse-reflectance NIR.</p>
        <a class="det-link" href="#det-snv">&#9660; algorithm details</a>
    </div>

    <!-- ---- MSC ---- -->
    <div class="cat">
        <h3>Scatter corr. (MSC) &nbsp;<span class="fm">(I &minus; a) / b vs. &Icirc;</span></h3>
        <p>Multiplicative Scatter Correction — fits each spectrum to the mean spectrum by linear
        regression and removes the fitted offset and slope. More physically interpretable than
        SNV when a meaningful reference exists. Requires at least ~5 spectra.</p>
        <p>By default the regression is fit using the <em>whole</em> spectrum — the classical
        formulation, appropriate when most of the range is scatter-dominated. Check
        <strong>"Fit regression within region only"</strong> (shown only for this method) to
        restrict the fit to the defined normalization region instead, e.g. a known
        scatter-only window with no real absorption — this can give a cleaner fit if you have
        such a window, but a poorer one if the region is too narrow or unrepresentative.
        Either way, the resulting correction is applied to the full spectrum.</p>
        <a class="det-link" href="#det-msc">&#9660; algorithm details</a>
    </div>

    <hr>
    <h2>Quick selection guide</h2>
    <table>
        <tr><th>Situation</th><th>Recommended method</th></tr>
        <tr><td>Comparing Raman spectra, different laser power or integration time</td>
            <td>Peak intensity or Vector norm</td></tr>
        <tr><td>Quantitative band-ratio / composition analysis</td>
            <td>Area (integral)</td></tr>
        <tr><td>Noisy spectra or cosmic rays present</td>
            <td>Robust peak or Mean of top N%</td></tr>
        <tr><td>Broad or flat-topped peak as reference</td>
            <td>Mean of top N%</td></tr>
        <tr><td>Dividing by blank or instrument response</td>
            <td>Reference spectrum</td></tr>
        <tr><td>Solid-sample Raman or powder NIR — particle size variation</td>
            <td>Scatter corr. (SNV)</td></tr>
        <tr><td>Diffuse-reflectance NIR — scatter correlated with absorption</td>
            <td>Scatter corr. (MSC)</td></tr>
        <tr><td>Large mapping dataset with systematic drift</td>
            <td>SVD factor norm.</td></tr>
        <tr><td>Shape comparison only, absolute intensity irrelevant</td>
            <td>Min-max [0, 1]</td></tr>
        <tr><td>CD or absorption spectra — zero baseline in silent region (e.g. 320&ndash;330&nbsp;nm)</td>
            <td>Offset correction</td></tr>
    </table>

    <p>For the five Result-scaling-eligible methods (Peak intensity, Area, Vector
    norm, Robust peak, Mean of top N%) or for SVD factor normalization, check the
    <a href="#factors">Per-spectrum factors</a> table in the Preview tab to verify no
    spectrum's factor is an outlier before trusting the normalization.</p>

    <hr>

    <!-- ================================================================ -->
    <!-- DETAILED ALGORITHM SECTIONS                                       -->
    <!-- ================================================================ -->

    <h2>Algorithm details</h2>
    <p>The sections below describe exactly what the software computes for each method,
    including the Python/NumPy calls used internally.</p>

    <!-- ---- Peak intensity detail ---- -->
    <div class="detail">
        <a name="det-peak"></a>
        <h3>Peak intensity — algorithm</h3>
        <p><strong>Step 1 — build the region mask:</strong>
        A boolean array is created that is <span class="fm">True</span> for every x-axis
        point that falls within the selected region(s). In Include mode the union of all
        regions is used; in Exclude mode the complement of that union is used.</p>
        <p><strong>Step 2 — find the maximum:</strong>
        <span class="fm">I_max = numpy.max(y[mask])</span><br>
        The single highest intensity value within the masked region.</p>
        <p><strong>Step 3 — divide the full spectrum:</strong>
        <span class="fm">y_norm = y / I_max</span><br>
        Applied to every point in the spectrum, not just the region.</p>
        <p><em>Edge case:</em> if <span class="fm">I_max = 0</span> the spectrum is
        returned unchanged.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Area detail ---- -->
    <div class="detail">
        <a name="det-area"></a>
        <h3>Area (integral) — algorithm</h3>
        <p><strong>Step 1 — build the region mask</strong> (same as above).</p>
        <p><strong>Step 2 — compute the area by the trapezoidal rule:</strong>
        <span class="fm">A = numpy.trapezoid(y[mask], x[mask])</span><br>
        Each pair of adjacent points forms a trapezoid; their areas are summed.
        The trapezoidal rule is exact for linearly interpolated data and handles
        non-uniform x-axis spacing correctly (important for spectrometers with
        non-uniform dispersion).</p>
        <p>The result has units of intensity &times; x-axis unit
        (e.g. counts&middot;cm<sup>&minus;1</sup>), so it is physically meaningful
        as the integrated band intensity.</p>
        <p><strong>Step 3 — divide the full spectrum:</strong>
        <span class="fm">y_norm = y / A</span></p>
        <p><em>Edge case:</em> if <span class="fm">A = 0</span> the spectrum is
        returned unchanged.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Vector norm detail ---- -->
    <div class="detail">
        <a name="det-vector"></a>
        <h3>Vector norm (L2) — algorithm</h3>
        <p><strong>Step 1 — build the region mask</strong> (same as above).</p>
        <p><strong>Step 2 — compute the Euclidean norm over the region:</strong>
        <span class="fm">L = numpy.linalg.norm(y[mask])</span><br>
        Equivalent to <span class="fm">sqrt(y[0]&sup2; + y[1]&sup2; + &hellip; + y[n]&sup2;)</span>
        summed over the masked points only.</p>
        <p>Geometrically, this treats the masked spectrum as a vector in
        N-dimensional space and measures its length. Dividing by L rescales the
        vector to unit length while preserving the direction — i.e. all relative
        peak heights are kept exactly.</p>
        <p>Because it uses every point in the region (not just the maximum), it is
        more stable than peak-based methods when the tallest peak varies slightly
        between measurements.</p>
        <p><strong>Step 3 — divide the full spectrum:</strong>
        <span class="fm">y_norm = y / L</span></p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Robust peak detail ---- -->
    <div class="detail">
        <a name="det-quantile"></a>
        <h3>Robust peak (Nth percentile) — algorithm</h3>
        <p><strong>Step 1 — build the region mask</strong> (same as above).</p>
        <p><strong>Step 2 — compute the Nth percentile:</strong>
        <span class="fm">P = numpy.percentile(y[mask], N)</span><br>
        P is the intensity value such that N% of the points in the region lie
        below it. With the default N&nbsp;=&nbsp;95, exactly 5% of points
        (the potential outliers / noise spikes) are above P.</p>
        <p>For a sharp, well-resolved Raman peak, P&nbsp;&asymp;&nbsp;I<sub>max</sub>
        of the true peak. For a noisy spectrum, P ignores the few points that happen
        to be highest due to noise, giving a more reproducible normalization factor.</p>
        <p><strong>Step 3 — divide the full spectrum:</strong>
        <span class="fm">y_norm = y / P</span></p>
        <p><em>Choosing N:</em> N&nbsp;=&nbsp;95 (default) works for most cases.
        For very spiky data lower N (e.g. 90) gives more robustness; for clean data
        N can be raised toward 99 to approach the true maximum.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Mean of top N% detail ---- -->
    <div class="detail">
        <a name="det-topmean"></a>
        <h3>Mean of top N% — algorithm</h3>
        <p><strong>Step 1 — build the region mask</strong> (same as above).</p>
        <p><strong>Step 2 — find the Nth percentile threshold:</strong>
        <span class="fm">threshold = numpy.percentile(y[mask], N)</span></p>
        <p><strong>Step 3 — select points above the threshold and average them:</strong>
        <span class="fm">top = y[mask][y[mask] &ge; threshold]</span><br>
        <span class="fm">factor = numpy.mean(top)</span><br>
        This keeps the top (100&minus;N)% of points and averages them.
        With N&nbsp;=&nbsp;95 the top 5% of points are averaged.</p>
        <p><strong>Why this is better than the plain percentile for broad peaks:</strong>
        The percentile method picks a single threshold value that may sit on the
        flank of a broad or flat-topped band. The mean-of-top-N% averages all the
        points that actually constitute the peak top, giving a more stable and
        physically meaningful estimate of the peak intensity.</p>
        <p><strong>Step 4 — divide the full spectrum:</strong>
        <span class="fm">y_norm = y / factor</span></p>
        <p><em>Choosing N:</em> same guidance as for Robust peak — N&nbsp;=&nbsp;95
        is the default. The two methods share the same N spinbox in the dialog.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Min-max detail ---- -->
    <div class="detail">
        <a name="det-minmax"></a>
        <h3>Min-max [0, 1] — algorithm</h3>
        <p><strong>Step 1 — build the region mask</strong> (same as for other region-based methods).</p>
        <p><strong>Step 2 — find min and max over the region:</strong><br>
        <span class="fm">min_val = numpy.min(y[mask])</span><br>
        <span class="fm">max_val = numpy.max(y[mask])</span></p>
        <p><strong>Step 3 — apply the same linear rescaling to the full spectrum:</strong><br>
        <span class="fm">y_norm = (y &minus; min_val) / (max_val &minus; min_val)</span><br>
        The region itself spans [0, 1]. Points outside the region are shifted and scaled
        by the same amount and may fall outside [0, 1].</p>
        <p><em>Baseline sensitivity:</em> because the minimum enters the formula, any DC
        baseline offset shifts the result. A spectrum with the same shape but a higher
        baseline will have a different y_norm. Apply baseline correction before using this
        method if you want to compare shapes independently of baseline.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Offset correction detail ---- -->
    <div class="detail">
        <a name="det-offset"></a>
        <h3>Offset correction — algorithm</h3>
        <p><strong>Step 1 — define the silent region</strong> using the normalization region
        controls (e.g. From&nbsp;=&nbsp;320, To&nbsp;=&nbsp;330&nbsp;nm for CD/absorption).</p>
        <p><strong>Step 2 — compute the mean over that region:</strong><br>
        <span class="fm">offset = numpy.mean(y[mask])</span><br>
        where <em>mask</em> selects points within the defined region.</p>
        <p><strong>Step 3 — subtract the offset from the full spectrum:</strong><br>
        <span class="fm">y_norm = y &minus; offset</span><br>
        The same scalar is subtracted from every point. No division, no scaling.</p>
        <p><em>Why a region and not the whole spectrum?</em> If you subtract the mean of
        the entire spectrum you also remove real signal. The key is to pick a region that
        is physically expected to be zero — the flat, signal-free tail beyond the last
        chromophore absorption band. For most CD and UV-Vis work this is typically
        above 320&nbsp;nm.</p>
        <p><em>Multiple regions:</em> if more than one region is defined, the mask is
        the union of all regions. The mean of all selected points is used as the offset.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- Reference spectrum detail ---- -->
    <div class="detail">
        <a name="det-ref"></a>
        <h3>Reference spectrum — algorithm</h3>
        <p><strong>Step 1 — select the reference:</strong>
        The "Reference spectrum" dropdown lists every spectrum loaded into the dialog by
        its actual label, in the order spectra were loaded (not the possibly-resorted
        order shown in the Selected spectra list). The dropdown's selected position
        already corresponds directly to the 0-based Python list index used internally —
        no offset conversion is needed.</p>
        <p><strong>Step 2 — point-wise division:</strong>
        <span class="fm">y_norm = y / y_ref</span><br>
        Each point is divided by the corresponding point of the reference spectrum.
        Zero values in the reference are replaced by 1&times;10<sup>&minus;10</sup>
        to avoid division by zero.</p>
        <p><em>Requirement:</em> the reference and all processed spectra must have
        exactly the same number of points and the same x-axis grid. If they differ
        (e.g. after a data-range operation that cropped one spectrum differently),
        the spectrum is returned unchanged.</p>
        <p><em>Result scaling:</em> not available for this method — see
        <a href="#scaling">Result scaling</a> above for why.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- SNV detail ---- -->
    <div class="detail">
        <a name="det-snv"></a>
        <h3>Scatter corr. (SNV) — algorithm</h3>
        <p><strong>Step 1 — build the region mask</strong> (same as above).</p>
        <p><strong>Step 2 — compute mean and standard deviation over the region:</strong><br>
        <span class="fm">&mu; = numpy.mean(y[mask])</span><br>
        <span class="fm">&sigma; = numpy.std(y[mask])</span></p>
        <p><strong>Step 3 — centre and scale the full spectrum:</strong><br>
        <span class="fm">y_norm = (y &minus; &mu;) / &sigma;</span><br>
        Subtraction of &mu; removes additive baseline offset;
        division by &sigma; removes multiplicative scatter.</p>
        <p><em>Important:</em> unlike intensity normalization, SNV changes both
        the scale <em>and</em> the zero level of the spectrum. The output has
        no physical intensity unit — it is a dimensionless standardised score.
        Do not compare absolute values between SNV-processed spectra and raw spectra.</p>
        <p><em>Edge case:</em> if <span class="fm">&sigma;&nbsp;=&nbsp;0</span>
        (all points identical), only mean-centering is applied.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- MSC detail ---- -->
    <div class="detail">
        <a name="det-msc"></a>
        <h3>Scatter corr. (MSC) — algorithm</h3>
        <p><strong>Step 1 — compute the mean spectrum:</strong>
        <span class="fm">&Icirc; = numpy.mean(all_spectra, axis=1)</span><br>
        The column-wise mean across all spectra in the batch (each column is one spectrum),
        computed from the <em>full</em> spectra regardless of any region.</p>
        <p><strong>Step 2 — linear regression of each spectrum against the mean:</strong><br>
        The model is <span class="fm">y = a + b &middot; &Icirc;</span>.
        With <strong>"Fit regression within region only"</strong> unchecked (default), the
        coefficients are found by ordinary least squares over every point:<br>
        <span class="fm">A = [[1, &Icirc;[0]], [1, &Icirc;[1]], &hellip;]</span><br>
        <span class="fm">[a, b] = numpy.linalg.lstsq(A, y)</span><br>
        With the checkbox checked, <span class="fm">&Icirc;</span> and <span class="fm">y</span>
        are first restricted to the points inside the defined normalization region (the same
        region mask used by every other region-based method) before the same least-squares
        fit is run on that subset only.</p>
        <p><strong>Step 3 — correct the spectrum:</strong>
        <span class="fm">y_norm = (y &minus; a) / b</span><br>
        This removes the fitted additive scatter (a) and multiplicative scatter (b),
        mapping the spectrum back onto the scale of the mean spectrum. This step always
        applies to the <em>entire</em> spectrum, regardless of whether the fit in Step 2
        used the whole spectrum or just the region.</p>
        <p><em>Edge case:</em> if <span class="fm">b&nbsp;=&nbsp;0</span> or the
        least-squares system is singular, the spectrum is returned unchanged.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <!-- ---- SVD detail ---- -->
    <div class="detail">
        <a name="det-svd"></a>
        <h3>SVD factor norm. — algorithm</h3>
        <p><strong>Step 1 — build the spectra matrix:</strong>
        All spectra are stacked as columns: matrix shape is
        (n_wavelengths &times; n_spectra). If a normalization region is defined, each
        spectrum is first multiplied by the region mask (zeroing everything outside the
        region) before being placed in the matrix — so the decomposition in Step 2 sees
        only the selected region's data, and the region choice does affect the result.</p>
        <p><strong>Step 2 — singular value decomposition:</strong><br>
        <span class="fm">U, S, V<sup>T</sup> = numpy.linalg.svd(matrix)</span><br>
        U contains the spectral basis vectors (subspectra),
        S contains the singular values,
        V<sup>T</sup> contains the per-spectrum coefficients (loadings).</p>
        <p><strong>Step 3 — extract first-component loadings:</strong><br>
        <span class="fm">V<sub>1</sub> = V<sup>T</sup>[0, :]</span> &nbsp;(first row of V<sup>T</sup>)<br>
        These loadings represent each spectrum's contribution to the dominant
        variation pattern in the dataset.</p>
        <p><strong>Step 4 — compute normalization factors:</strong><br>
        <span class="fm">factors = |V<sub>1</sub> / mean(V<sub>1</sub>)|</span><br>
        Dividing by the mean centres the factors around 1, so spectra that
        already match the mean spectrum are divided by ~1 (unchanged).</p>
        <p><strong>Step 5 — divide each spectrum by its factor:</strong><br>
        <span class="fm">y_norm[i] = y[i] / factors[i]</span></p>
        <p><em>Explained variance</em> (ratio of S[0]&sup2; to &sum;S&sup2;) is stored
        in the pipeline metadata and visible in the operation log. A high explained
        variance (&gt;&nbsp;90%) means the first component captures most of the
        variation and the correction is well-founded.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    this dialog's own spectrum list.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body>
    </html>
    """)
    return help_template.substitute(images)
