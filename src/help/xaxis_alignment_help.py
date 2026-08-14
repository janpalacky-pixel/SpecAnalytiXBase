# src/help/xaxis_alignment_help.py

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path

# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build — same mechanism as
# interactive_subtraction_help.py; see it for the full rationale. $KEY below
# resolves to a COMPLETE <img> tag (or a "not yet added" placeholder <div>)
# and is used bare in the template — no wrapping <img src="$KEY"> — since
# that double-wrapping is exactly what broke interactive_subtraction_help.py
# the first time around.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "x_axis_alignment")

_SCREENSHOT_FILES = {
    "OVERVIEW":     "dialog_overview.png",
    "SETTINGS":     "alignment_settings.png",
    "PREVIEW_ROW":  "run_preview_controls.png",
    "SHIFT_TABLE":  "shift_table.png",
    "SHIFT_PLOT":   "shift_plot.png",
    "COMMIT":       "commit_buttons.png",
}

_SCREENSHOT_ALT = {
    "OVERVIEW":    "X-Axis Alignment dialog overview",
    "SETTINGS":    "Alignment settings (Reference, Max shift, Interpolation) and Restrict alignment to x-range groupboxes",
    "PREVIEW_ROW": "Run preview button, View toggle, and 'Settings changed — re-run preview' label",
    "SHIFT_TABLE": "Shift table tab: statistics, per-spectrum shift table, Copy to clipboard and Export CSV buttons",
    "SHIFT_PLOT":  "Shift plot tab: per-spectrum shift values plotted",
    "COMMIT":      "Help, Apply, Add as New, and Close buttons",
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


def get_xaxis_alignment_help_title():
    return 'X-Axis Alignment — help'


def get_xaxis_alignment_help_content():
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
            .cat    { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .detail { background: #FAFAFA; border-left: 4px solid #E65100;
                      padding: 10px 14px; margin: 6px 0 14px 0; border-radius: 3px; }
            .tip    { background: #E8F5E9; border-left: 4px solid #2E7D32;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note   { background: #E3F2FD; border-left: 4px solid #1565C0;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn   { background: #FFF8E1; border-left: 4px solid #F9A825;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm     { font-family: monospace; background: #ececec;
                      padding: 1px 5px; border-radius: 3px; }
            .det-link  { font-size: 11px; color: #1565C0; }
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

    <h1>X-Axis Alignment</h1>

    <p>X-axis alignment corrects <em>systematic shifts of the wavenumber (or wavelength)
    scale</em> between spectra that are otherwise identical in shape. Such shifts arise
    from temperature-induced drift of the spectrometer optics, day-to-day variation in
    laser excitation wavelength, or small differences between instruments when the
    same sample is measured on multiple setups.</p>

    <p>The operation shifts the x-scale of each non-reference spectrum so that it
    best matches the chosen reference. In practice, the y-values are also
    slightly affected by the resampling step — see the
    <a href="#interp-effect">note on interpolation-induced shape changes</a> below.</p>

    <div class="screenshot">
        $OVERVIEW
        <p class="caption">The full dialog: selected spectra / alignment settings on the left, Spectra / Shift table / Shift plot tabs on the right.</p>
    </div>

    <div class="note">
        <strong>Typical pipeline position:</strong><br>
        Data range &rarr; Baseline correction &rarr; Normalization &rarr;
        <strong>X-axis alignment</strong> &rarr; further analysis (PCA, cluster analysis, band ratio&hellip;).<br>
        Align <em>after</em> normalization and baseline correction so that the spectra
        being compared are already on the same intensity scale — the optimiser converges
        more reliably on clean, flat-baseline data.
    </div>

    <div class="tip">
        <strong>Try it with the bundled demo dataset:</strong> a synthetic set of
        32 spectra sharing the same bands, each shifted by a different, known
        amount along x, is available under <b>Help &rarr; Test datasets &rarr;
        Synthetic &rarr; X-Axis Alignment</b> &mdash; a quick way to see the
        alignment in action without needing your own shifted spectra. Pick any
        one spectrum as the Reference and align the rest.
    </div>

    <hr>
    <h2>Workflow</h2>
    <ol>
        <li><strong>Select spectra</strong> — choose two or more spectra in the main window
            that share the same bands but may differ in their x-scale position.</li>
        <li><strong>Open Parameters</strong> — click the Parameters button in the
            Spectra Processing panel to open the X-Axis Alignment dialog.</li>
        <li><strong>Choose a reference spectrum</strong> — pick one spectrum from
            the Reference dropdown. This spectrum is returned unchanged; all others
            are shifted towards it.</li>
        <li><strong>Set Max shift</strong> — enter the largest drift you expect
            (in the same units as the x-axis, e.g. cm<sup>&minus;1</sup>).
            The optimiser searches in the range
            [&minus;max&nbsp;shift, +max&nbsp;shift].</li>
        <li><strong>Run preview</strong> — switch to the <em>Alignment preview</em>
            tab and click <em>&#9654;&nbsp;Run preview</em> to inspect the result
            before committing. The shift table and statistics are shown immediately.</li>
        <li><strong>Click Apply or Add as New</strong> — Apply replaces the spectra
            loaded in the dialog with their aligned result; Add as New leaves the
            originals untouched and adds the result to the spectra list under new
            names instead. Both commit immediately, with their own confirmation and
            result message shown right in the dialog — there is no separate Run step
            in the main window for this operation.</li>
    </ol>

    <div class="screenshot">
        $PREVIEW_ROW
        <p class="caption">The Run preview button and View toggle, with the "Settings changed — re-run preview" warning that appears whenever a setting changes after the last preview.</p>
    </div>

    <div class="tip">
        <strong>Apply vs. Add as New vs. Close:</strong>
        <ul>
            <li><strong>Apply</strong> replaces the spectra loaded in the dialog with
                their aligned result. The originals are overwritten once Apply runs.</li>
            <li><strong>Add as New</strong> leaves the originals completely untouched
                and adds the aligned result to the spectra list under new, unique names
                (e.g. <span class="fm">samplename_aligned</span>, with a number appended
                if that name is already taken).</li>
            <li><strong>Close</strong> closes the dialog without applying anything to the
                main window's spectra.</li>
        </ul>
        <p>Apply and Add as New close the dialog automatically once the commit succeeds, re-running
        the alignment with whatever settings are currently shown — whether or not you've clicked Run
        preview first, since Run preview exists purely so you can inspect the result before
        committing. Whatever settings were last shown are still remembered the next time you reopen
        the dialog for the same spectra, for example to try a different reference spectrum or max
        shift and commit again.</p>
    </div>

    <div class="screenshot">
        $COMMIT
        <p class="caption">Help, Apply, Add as New, and Close, at the bottom of the left panel.</p>
    </div>

    <div class="tip">
        <strong>Interpreting the shift table:</strong> shifts shown in
        <span style="color:#1565C0;">blue</span> are rightward (positive);
        shifts in <span style="color:#B71C1C;">red</span> are leftward (negative).
        If the Max |shift| statistic is close to your <em>Max shift</em> setting,
        the optimiser may have hit its bound — increase Max shift and re-run the
        preview.
    </div>

    <div class="screenshot">
        $SHIFT_TABLE
        <p class="caption">Shift table tab: statistics summary, per-spectrum shift/direction/role table, and Copy to clipboard / Export CSV.</p>
    </div>

    <div class="screenshot">
        $SHIFT_PLOT
        <p class="caption">Shift plot tab: the same per-spectrum shifts, plotted, with its own label display options in the left panel.</p>
    </div>

    <div class="tip">
        <a name="shift-plot-display"></a>
        <strong>Shift plot display options</strong> appear in the left panel
        whenever the Shift plot tab is the active one (hidden the rest of the
        time — the Spectra and Shift table tabs don't use them):
        <ul>
            <li><strong>Label rotation</strong> and <strong>Label font
                size</strong> (Auto shrinks as the number of spectra grows,
                or pick a fixed size) control how the per-spectrum labels
                along the x-axis are drawn.</li>
            <li><strong>Full label / First N chars / Last N chars</strong>
                truncates long labels, keeping only the first or last
                <em>N</em> characters (set with the N spinbox next to it) —
                useful once labels no longer fit legibly at the chosen font
                size.</li>
            <li><strong>Use spectrum index</strong> replaces labels with
                plain position numbers (1, 2, 3, &hellip;) instead — the same
                numbering used in the Shift table's rows. Disables the
                truncation controls above, since there's nothing left to
                truncate.</li>
        </ul>
        These honor this dialog's own <strong>Shorten names</strong> checkbox
        first (see below), then apply truncation on top of whatever that
        produces.
    </div>

    <hr>
    <h2 id="settings">Settings reference</h2>

    <table>
        <tr>
            <th>Setting</th>
            <th>Description</th>
            <th>Recommended value</th>
        </tr>
        <tr>
            <td><strong>Reference spectrum</strong></td>
            <td>The spectrum against which all others are aligned.
                Returned unchanged (shift&nbsp;=&nbsp;0). Choose one with a
                high signal-to-noise ratio and clear, well-separated bands.</td>
            <td>The best-quality spectrum or an external calibration standard.</td>
        </tr>
        <tr>
            <td><strong>Max shift</strong></td>
            <td>Search bound for the optimiser (x-units). The optimal shift is
                found within [&minus;max, +max]. Setting this too small risks
                the optimiser being trapped; too large may allow unphysical
                solutions for noisy spectra.</td>
            <td>2&ndash;15&nbsp;cm<sup>&minus;1</sup> for Raman; 0.5&ndash;5&nbsp;nm
                for UV-Vis / fluorescence.</td>
        </tr>
        <tr>
            <td><strong>Interpolation</strong></td>
            <td>Method used to evaluate y-values at shifted x-positions.
                <em>cubic</em> (default) is smooth and accurate for well-sampled
                spectra. <em>linear</em> is faster and numerically stable for
                very noisy or sparsely sampled data.</td>
            <td><em>cubic</em> for most Raman / IR work.</td>
        </tr>
        <tr>
            <td><strong>Restrict to x-range</strong></td>
            <td>When checked, the RMSD used by the optimiser is computed only
                over this sub-range. Useful when the full spectrum contains
                broad fluorescence or solvent bands that would distort the
                shift estimate. Leave unchecked to use the full overlap region.</td>
            <td>A sharp, isolated band or a flat silent region shared by
                all spectra.</td>
        </tr>
    </table>

    <div class="screenshot">
        $SETTINGS
        <p class="caption">Alignment settings (Reference, Max shift, Interpolation) and the checkable "Restrict alignment to x-range" groupbox, stacked in the left panel.</p>
    </div>

    <hr>
    <h2 id="algorithm">Algorithm</h2>

    <p>The alignment is performed independently for each non-reference spectrum.
    For a test spectrum <em>T</em> and reference spectrum <em>R</em>, the optimal
    shift &delta; is defined as:</p>

    <div class="cat">
        <p><span class="fm">&delta;* = argmin<sub>&delta;</sub> RMSD(&delta;)</span></p>
        <p><span class="fm">RMSD(&delta;) = &radic;[ mean( (T_interp(x &minus; &delta;) &minus; R(x))<sup>2</sup> ) ]</span></p>
        <p>where the mean is taken over all x-points of <em>R</em> that fall
        inside the overlap region after shifting.</p>
    </div>

    <h3>Step 1 — coarse grid search</h3>
    <p>21 evenly-spaced shift values spanning
    [&minus;max&nbsp;shift, +max&nbsp;shift] are evaluated. The RMSD at each
    point is computed using the chosen interpolation. The lowest-cost point is
    used as the starting value for the fine optimisation.</p>

    <h3>Step 2 — Nelder-Mead refinement</h3>
    <p>The Nelder-Mead simplex method
    (<span class="fm">scipy.optimize.minimize(..., method='Nelder-Mead')</span>)
    refines the shift to a tolerance of 10<sup>&minus;6</sup> x-units.
    This is the direct Python equivalent of MATLAB's
    <span class="fm">fminsearch</span>.
    Convergence is typically achieved in fewer than 200 function evaluations
    per spectrum.</p>

    <h3>Step 3 — resample onto the reference grid</h3>
    <p>Once &delta;* is found, the test spectrum is re-sampled onto the
    reference x-grid using
    <span class="fm">scipy.interpolate.interp1d</span> with the chosen
    interpolation. Only the overlapping x-range is retained; edge points
    outside the overlap are dropped. The reference spectrum is returned
    without any modification.</p>

    <div class="note">
        <a name="interp-effect"></a>
        <strong>Expected minor shape change after alignment.</strong><br>
        Resampling the y-values onto a shifted x-grid introduces small
        interpolation errors, so the spectral shape is not perfectly preserved.
        Two effects contribute:
        <ul>
            <li><strong>Interpolation error.</strong>
                Each y-value at a new x position is estimated from neighbouring
                points. Cubic spline is the most accurate for smooth Raman bands
                but can produce tiny oscillations near sharp features or steep
                edges. Linear interpolation avoids oscillations but introduces
                kinks. The effect is proportional to the shift magnitude and
                inversely proportional to the number of data points per band —
                for typical Raman spectra with dense, uniform sampling and small
                shifts (&lt;&nbsp;5&nbsp;data-point widths) the shape change is
                below the noise level.</li>
            <li><strong>Edge trimming.</strong>
                Each shifted spectrum is trimmed to its overlap with the
                reference. If different spectra have different shifts, they end
                up with slightly different x-extents, and the outermost data
                points may change between runs. Apply
                <strong>Data range</strong> with linearisation after alignment
                to bring all spectra onto a single uniform grid.</li>
        </ul>
        To minimise interpolation artefacts: prefer <em>cubic</em>
        interpolation, ensure at least 5&nbsp;points per FWHM, and keep shifts
        small by choosing a reference spectrum that is already close to the
        group mean.
    </div>

    <div class="detail">
        <a name="det-interp"></a>
        <h3>Interpolation methods — details</h3>
        <table>
            <tr><th>Method</th><th>Polynomial order</th><th>When to use</th></tr>
            <tr>
                <td><strong>cubic</strong></td>
                <td>3 (piecewise cubic spline)</td>
                <td>Default. Smooth, accurate derivative. Best for spectra with
                    gradually varying bands sampled at &ge;&nbsp;5 points per
                    FWHM.</td>
            </tr>
            <tr>
                <td><strong>quadratic</strong></td>
                <td>2</td>
                <td>Intermediate between linear and cubic. Rarely needed.</td>
            </tr>
            <tr>
                <td><strong>linear</strong></td>
                <td>1</td>
                <td>Fastest; no overshoot. Preferred for very noisy spectra
                    or data with fewer than 5 points per band.</td>
            </tr>
        </table>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <hr>
    <h2 id="prereqs">Prerequisites and limitations</h2>

    <div class="warn">
        <strong>What x-axis alignment does NOT correct:</strong>
        <ul>
            <li>Differences in spectral <em>resolution</em> (different slit widths).</li>
            <li>Non-uniform stretching or compression of the x-axis
                (calibration polynomial errors).</li>
            <li>Intensity or baseline differences — normalise and correct the
                baseline separately before aligning.</li>
            <li>Large shifts that compress the overlap region to fewer than ~10 points;
                the RMSD becomes unreliable in such cases.</li>
        </ul>
    </div>

    <div class="tip">
        <strong>Best-practice checklist before running alignment:</strong>
        <ul>
            <li>Apply <strong>Data range</strong> to give all spectra the same x-axis
                extent.</li>
            <li>Apply <strong>Baseline correction</strong> so that the RMSD measures
                band similarity, not baseline offset.</li>
            <li>Apply <strong>Normalization</strong> (peak intensity or area) so that
                intensity scale does not bias the shift estimate.</li>
            <li>Remove cosmic rays (<strong>Spike removal</strong>) — isolated spikes
                can attract the optimiser to a spurious shift.</li>
            <li>Choose a reference spectrum with a high SNR and at least two
                well-resolved bands for an unambiguous fit.</li>
        </ul>
    </div>

    <hr>
    <h2 id="output">Output</h2>

    <p>After clicking <strong>Apply</strong> in the main window:</p>
    <ul>
        <li>Each aligned spectrum receives an updated <span class="fm">x_scale</span>
            trimmed to the overlap with the reference. Use <strong>Add as
            New</strong> instead of Apply if you want to keep the
            unaligned spectrum around as a separate entry.</li>
        <li>An <span class="fm">xaxis_alignment_info</span> dict is stored in each
            spectrum containing: <span class="fm">shift</span>,
            <span class="fm">is_reference</span>,
            <span class="fm">reference_label</span>, and
            <span class="fm">interpolation_method</span>.</li>
        <li>The operation is registered in the pipeline history and can be reviewed
            in the <strong>Summary</strong> dialog.</li>
    </ul>

    <div class="warn">
        <strong>Important &mdash; x-axes may differ slightly after alignment.</strong><br>
        Because each spectrum is shifted by a different amount and trimmed to the
        overlap region with the reference, the resulting spectra may end up on
        slightly different x-grids (different start/end points or number of points).
        Operations that require all spectra to share an <em>identical</em> x-axis
        &mdash; such as <strong>SVD background correction</strong> and
        <strong>Spectral calculator</strong> &mdash; will fail or give incorrect
        results if applied directly after alignment.<br><br>
        <strong>Solution:</strong> apply <strong>Data range</strong> with
        <em>linearisation enabled</em> after alignment. This resamples all spectra
        onto a single uniform x-grid with identical start, end, and step size.
        Set the range to the common overlap window and choose a suitable number
        of points (or step size). Once linearised, SVD background correction,
        Spectral calculator, and any other operation requiring a shared x-axis
        will work correctly.
    </div>

    <hr>
    <h2 id="faq">Frequently asked questions</h2>

    <h3>The shifts look too large / the alignment made things worse.</h3>
    <p>The most common cause is an unsuitable reference spectrum (low SNR, broad
    featureless bands, or a large fluorescence background that dwarfs the Raman
    signal). Choose a reference with sharp, well-resolved peaks and a flat baseline.
    If spectra have very different intensities, normalise them first.</p>

    <h3>Max |shift| in the statistics bar equals my Max shift setting.</h3>
    <p>The optimiser reached its bound without finding a minimum inside it. Increase
    <em>Max shift</em> and re-run the preview. If the result still looks wrong, the
    spectra may have a non-shift difference (resolution, calibration polynomial) that
    this operation cannot correct.</p>

    <h3>Can I align spectra with different x-axis lengths?</h3>
    <p>Yes. After alignment each spectrum is re-sampled onto the reference x-grid
    within the overlapping range, so spectra that started with different extents
    will all end up on the same grid. If you need identical lengths across the
    whole range, apply a <strong>Data range</strong> step first to crop to a common
    window.</p>

    <h3>Does the reference spectrum change?</h3>
    <p>No. The reference is returned exactly as it was passed in — same x-scale,
    same y-values. Only the other spectra are modified.</p>

    <h3>How do I use the x-range restriction?</h3>
    <p>Check <em>Restrict alignment to x-range</em> and enter the boundaries of a
    spectral region that contains a clear, isolated band shared by all spectra.
    The RMSD will be computed only inside this window, ignoring parts of the spectrum
    that may be dominated by fluorescence, solvent, or noise. This often improves
    alignment accuracy when the full spectrum is contaminated by interference.</p>

    <h3>SVD background correction / Spectral calculator fails after alignment. Why?</h3>
    <p>These operations require all spectra to share an identical x-axis (same number
    of points, same start and end values). After alignment, spectra are trimmed to the
    overlap window individually, so their x-grids may differ by a few points.
    Apply <strong>Data range</strong> with linearisation enabled immediately after
    alignment — set the range to the common overlap window and choose the desired
    number of points. All spectra will then be on the same uniform grid and the
    downstream operations will work correctly.</p>

    <h3>Why do the Shift table and Shift plot tabs appear only after Run preview?</h3>
    <p>They are populated entirely by the preview computation, so they are only
    shown once results are available. If you change any computation parameter
    (reference spectrum, max shift, interpolation method, or x-range restriction)
    the result tabs are removed and the stale warning appears — re-run the preview
    to repopulate them with up-to-date results.</p>

    <h3>Are preview results remembered if I close and re-open the dialog?</h3>
    <p>Yes. The last preview result is cached together with the settings that
    produced it. When you re-open the dialog with the same computation parameters,
    the cached alignment is restored automatically and the result tabs reappear
    without needing to re-run the preview. If any computation parameter has changed
    since the last run, the cache is discarded and you must run the preview again.</p>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox &mdash; separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies
    everywhere this dialog shows a spectrum label: the spectrum list, the
    <strong>Reference</strong> dropdown, and the Shift plot's x-axis labels
    (subject to whatever truncation / Use spectrum index setting is chosen
    there — see <a href="#shift-plot-display">Shift plot display options</a>
    above). It only affects what is <em>displayed</em> — spectrum identity,
    and any name written into a new or exported spectrum, is always the full
    original label. Toggling the main window's Shorten names checkbox has no
    effect on this dialog.</p>

    </body>
    </html>
    """)
    return help_template.substitute(images)
