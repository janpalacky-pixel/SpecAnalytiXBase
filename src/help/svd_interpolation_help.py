# src/help/svd_interpolation_help.py

"""
Help content for the SVD Interpolation operation.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "svd_interpolation")

_SCREENSHOT_FILES = {
    "OVERVIEW":      "dialog_overview.png",
    "PARAM_VALUES":  "parameter_values.png",
    "COMPONENTS":    "components_curve_fit.png",
    "GUESS":         "guess_components.png",
    "SUBSPECTRUM":   "subspectrum_checkbox.png",
    "TARGET_VALUES": "target_values.png",
    "PREVIEW":       "preview_tab.png",
    "COMMIT":        "commit_buttons.png",
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


def get_svd_interpolation_help_title():
    return 'SVD Interpolation — help'


def get_svd_interpolation_help_content():
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which
    # would collide with .format()-style placeholders.
    help_template = Template("""
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            .cat  { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note { background: #E3F2FD; border-left: 4px solid #1565C0;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn { background: #FFF8E1; border-left: 4px solid #F9A825;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm   { font-family: monospace; background: #ececec;
                    padding: 1px 5px; border-radius: 3px; }
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

    <h1 id="top">SVD Interpolation</h1>
    <p>Generates <strong>new, artificial spectra</strong> at parameter values you
    never actually measured — for example, spectra measured at temperatures
    5&deg;C to 90&deg;C in 5&deg; steps can be used to synthesize a spectrum at
    22&deg;C or 37&deg;C, without measuring it. Lives under
    <strong>Data Manipulation</strong> because, like Normalization or X-axis
    alignment, its output is new spectra ready for further processing — not an
    analysis result.</p>

    <div class="screenshot">
        <img src="$OVERVIEW" width="${OVERVIEW_W}" height="${OVERVIEW_H}" alt="SVD Interpolation dialog overview" />
        <p class="caption">The full dialog: settings on the left (scrollable), Coefficient curve / Preview tabs on the right.</p>
    </div>

    <div class="note"><strong>Requires a shared x-axis.</strong> Every selected
    spectrum must already be sampled on the same x-axis (use Data Range first
    if they aren't) — this is the same requirement SVD Analysis, PCA, MCR-ALS,
    NMF and Cluster Analysis all share, for the same reason: SVD stacks the
    spectra into one matrix, and that only makes sense column-by-column if
    every row means the same x-position.</div>

    <h2>The idea</h2>
    <p>SVD decomposes your data matrix into a small set of <strong>subspectra</strong>
    (shape patterns, columns of <span class="fm">U</span>) and, for each one, a
    <strong>coefficient</strong> per input spectrum (rows of <span class="fm">V<sup>T</sup></span>)
    saying how much of that subspectrum is present in each measurement. If your
    spectra were measured across a range of some parameter (temperature, pH,
    time, concentration&hellip;), each coefficient is really a smooth function of
    that parameter — a temperature-dependent shape change shows up as a
    temperature-dependent coefficient.</p>
    <p>This tool lets you sketch that function by hand for each relevant
    component, using a simple polynomial or spline through a few points you
    place yourself. Once fitted, the curve can be evaluated at ANY parameter
    value — including ones you never measured — and a brand-new spectrum is
    assembled from the same subspectra, weighted by the curve's value there:</p>
    <p style="text-align:center;"><span class="fm">
        new spectrum(v) = &sum;<sub>k selected</sub>&nbsp; U[:, k] &times; S[k] &times; coefficient<sub>k</sub>(v)
    </span></p>

    <h2>Step by step</h2>
    <h3>1. Parameter values</h3>
    <p>Enter the value each selected spectrum was actually measured at (e.g. its
    temperature), and a name for the parameter (shown as the axis label on the
    coefficient plots) — or click <strong>From file</strong> to load them from a
    text file instead (one value per line, same order as the spectra; a leading
    index column is tolerated, the last number on each line is used). Either
    way, click <strong>Apply parameter values</strong> to confirm them — this is
    required before any curve can be fit. Order doesn't matter: values can be
    entered in any order, and the underlying SEQUENCE doesn't have to be
    monotonic either — a heating/cooling ramp that goes up and then back down
    (e.g. <span class="fm">5, 10, 15, &hellip; 90, 80, 70, &hellip; 10, 5</span>)
    is handled correctly. This only affects how points get PLOTTED, not the
    data itself: nothing about your spectra or their values changes — points
    are simply drawn left-to-right by value, so the curve traces a clean
    left-to-right line instead of zig-zagging back and forth if they were
    drawn in original measurement order. The table supports the usual
    copy/cut/paste/delete shortcuts (Ctrl+C/X/V/Delete), including from an
    external spreadsheet.</p>
    <div class="tip"><strong>Repeated values are fine too</strong> — in that
    same ramp example, revisiting 90&rarr;80&rarr;&hellip; on the way back
    down means some temperatures (e.g. 80, 70, 60&hellip;) are shared by TWO
    spectra. Those pairs' coefficients are averaged together into one point
    before fitting, since an exact-fit spline (smoothing 0) can't pass
    through two different values at one x anyway.</div>
    <div class="warn">Clicking <strong>Apply parameter values</strong> again
    after curve points already exist clears every component's points first
    (with a confirmation) — they were positioned against the OLD values, so
    leaving them in place would mix old and new data on the same curve. Redo
    Auto-fill / manual points afterward.</div>

    <div class="screenshot">
        <img src="$PARAM_VALUES" width="${PARAM_VALUES_W}" height="${PARAM_VALUES_H}" alt="Parameter values table with Apply and From file buttons" />
        <p class="caption">The parameter values table, with Apply parameter values and From file.</p>
    </div>

    <h3>2. Pick a component, shape its curve</h3>
    <p>No separate step for picking "relevant" components — same as Manual
    Baseline doesn't ask which spectra to "include" before you start clicking.
    Select a component from the list (highest explained variance first), and
    its true, measured coefficients appear as gray dots on the plot.
    <strong>Left-click</strong> the plot to add a point describing where you
    think the curve should pass; use these to trace a plausible trend through
    (or smooth over) the gray dots. <strong>Right-click</strong> removes
    whichever point is nearest to the click. A &#10003; appears next to any
    component that already has a curve (&ge;2 points) in the list. Percentages
    are shown to 4 decimal places, not 2 — with many spectra a component can
    read "100.0000% / 0.0000%" at 2 decimals while actually being 99.9600% /
    0.0380%, which matters when judging what's worth including.</p>

    <div class="screenshot">
        <img src="$COMPONENTS" width="${COMPONENTS_W}" height="${COMPONENTS_H}" alt="Component selector, Polynomial/Spline fit controls, point editing row, and auto-fill row" />
        <p class="caption">Component selector at top; Polynomial / Spline (with its Smoothing spinbox) below; Point editing On/Off with Clear points and the orange "?" help button; Auto-fill current and Auto fill first N components at the bottom.</p>
    </div>

    <div class="tip"><strong>Selection is implicit.</strong> Whichever
    components end up with a curve are the ones used in the final
    reconstruction — components you never touch are simply left out, exactly
    like Manual Baseline only corrects spectra you've actually placed points
    on. Points are remembered per component as you switch between them, so
    you can freely go back and forth.</div>

    <p><strong>Guess # of components</strong> (top of this section) opens a
    small separate window with a switchable diagnostic plot — Component
    variance, Singular values, or Residual error, each as a bar or line plot,
    log or linear scale — over the first 50 components. It's a visual aid
    only: nothing is picked or suggested for you, you judge where the plot
    drops off sharply and flattens out.</p>

    <div class="screenshot">
        <img src="$GUESS" width="${GUESS_W}" height="${GUESS_H}" alt="Guess number of components diagnostic dialog" />
        <p class="caption">Guess # of components: switchable metric, bar/line style, log/linear scale.</p>
    </div>

    <p><strong>Auto-fill current</strong> places a point at every measured
    (parameter, coefficient) pair for the selected component and switches it
    to Spline with smoothing 0 — an exact fit through every measured point.
    <strong>Auto fill first N components</strong> does the same to several
    components at once. Worth knowing what this actually does:</p>
    <div class="tip">If you auto-fill EVERY component, the reconstruction at
    your measured parameter values will match the original spectra exactly —
    that's not a coincidence, it's just what SVD reconstruction means
    (&Sigma; U&middot;S&middot;V<sup>T</sup> reproduces the original data
    matrix exactly). So auto-fill's real value is entirely in the gaps
    <em>between</em> your measured values — that's the only place this tool
    does something a simple lookup table couldn't.</div>
    <p>Auto-fill reproduces each component's measured coefficients exactly,
    noise included. For low-weight components this is usually harmless — often
    desirable even, since the generated spectra end up carrying the same
    general noise character as your real data instead of looking artificially
    clean. It only becomes a real problem if the noise has a genuine pattern
    AND shows up in a statistically relevant (high-weight) component. Two ways
    to handle that: manually smooth just that component's curve (fewer,
    more deliberate points, or raise Spline smoothing above 0), or simply
    leave the outlier spectra out of the selection in the main window before
    running this tool at all. It's fine to auto-fill more components than
    "Guess # of components" would suggest — a low-weight component barely
    moves the reconstruction either way, so over-including costs little
    (same reasoning SVD Background's own denoising relies on elsewhere in
    this app).</p>
    <table>
        <tr><th>Fit type</th><th>When to use it</th></tr>
        <tr><td><span class="fm">Polynomial</span></td>
            <td>Smooth, simple trends — a gentle rise/fall/plateau. Degree 2
                (a gentle curve) is a reasonable starting point; raise it only
                if the trend genuinely has more bends than that, since higher
                degrees can swing wildly between points.</td></tr>
        <tr><td><span class="fm">Spline</span> (default)</td>
            <td>More flexible/local shape, or when you want the curve to pass
                through every point exactly (smoothing = 0). Increase smoothing
                if your points are a bit noisy and you want a gentler curve
                between them rather than a wiggly exact fit.</td></tr>
    </table>
    <div class="tip">The curve preview automatically extends to cover whatever
    target values you've typed in Step 3, so you can see exactly what an
    extrapolation beyond the measured range would look like before generating
    anything.</div>
    <div class="note"><strong>Extrapolation</strong> beyond your measured
    parameter range is really the main case where manual point placement
    still earns its keep over Auto-fill — Auto-fill has no opinion out there,
    a spline just continues on from its last segment. Manual points let you
    impose a trend you actually believe in, though it's inherently
    speculative either way and worth treating with some caution.</div>

    <p>Optionally, check <strong>Show subspectrum for this component</strong>
    (below the main plot, off by default — drag the splitter between the two
    plots to give it more room) to see the actual subspectrum (the U column)
    the selected component would contribute to reconstruction. Not usually
    needed, but a visibly noisy subspectrum can be a sign the component isn't
    statistically relevant — consistent with what the elbow plot would
    suggest, and it's the same shape that would actually get used, weighted
    by your fitted curve.</p>

    <div class="screenshot">
        <img src="$SUBSPECTRUM" width="${SUBSPECTRUM_W}" height="${SUBSPECTRUM_H}" alt="Show subspectrum checkbox and resulting subspectrum plot" />
        <p class="caption">Show subspectrum for this component, checked, with the resulting plot below the coefficient curve.</p>
    </div>

    <h3>3. Target values</h3>
    <p>Type the new parameter values you want spectra for (comma or newline
    separated, e.g. <span class="fm">22, 37, 42</span>), or set the start / end
    / step fields and click their <strong>Add</strong> button to append an
    evenly-spaced run of values (added on top of anything already typed, not
    replacing it). The orange <strong>?</strong> button repeats this
    explanation in-app.</p>

    <div class="screenshot">
        <img src="$TARGET_VALUES" width="${TARGET_VALUES_W}" height="${TARGET_VALUES_H}" alt="Target values text box and start/end/step range fields" />
        <p class="caption">Target values, typed or via the start / end / step range fields.</p>
    </div>

    <div class="warn"><strong>Extrapolation.</strong> Target values outside the
    range of your measured parameter values are allowed (that's the whole point
    for some use cases), but the further outside that range, the less trustworthy
    the result — the curve is a guess beyond the data it was fit to, same as any
    extrapolation.</div>
    <div class="note">A component needs at least 2 curve points before it's
    used — components with none (or just one) are simply left out of the
    reconstruction, with no warning needed, since that's the normal way to
    say "skip this one".</div>

    <h3>4. Preview &rarr; Save / Apply / Add as New</h3>
    <p>Switch to the <strong>Preview</strong> tab and click
    <strong>Compute Preview</strong> to see the resulting spectra — nothing is
    added to the main list yet, so you can freely check the result and adjust
    curves before committing to anything, and preview as many times as you
    like. Neither list is selected by default after computing — pick what you
    want to see using the multi-select lists below.</p>

    <div class="screenshot">
        <img src="$PREVIEW" width="${PREVIEW_W}" height="${PREVIEW_H}" alt="Preview tab with original/generated spectra lists and plot" />
        <p class="caption">The Preview tab: Original spectra / Generated spectra multi-select lists, legend controls, and the plot.</p>
    </div>

    <p>From here you have three independent options, all acting on whatever was
    most recently computed. <strong>Apply</strong> and <strong>Add as New</strong>
    both close this dialog once they succeed — same as every other Spectra
    Processing operation's Apply / Add as New pair. Use Compute Preview as many
    times as you like first to iterate on target values without committing to
    anything.</p>
    <ul>
        <li><strong>Save</strong> (next to Compute Preview) writes the
            generated spectra straight to a file (text, Excel, or individual
            files) via the app's normal Save dialog — without touching the
            main spectrum list at all, and without closing the dialog.</li>
        <li><strong>Apply</strong> (bottom-left of the dialog, below the
            groupboxes) removes the source spectra that fed the SVD basis
            (the ones you selected before opening this dialog) from the main
            list and adds the interpolated spectra in their place — asks for
            confirmation first, since this removes spectra.</li>
        <li><strong>Add as New</strong> (next to Apply) keeps the source
            spectra untouched and adds the interpolated spectra to the main
            list alongside them, under generated names.</li>
    </ul>

    <div class="screenshot">
        <img src="$COMMIT" width="${COMMIT_W}" height="${COMMIT_H}" alt="Apply, Add as New, Close, and Help buttons" />
        <p class="caption">Apply, Add as New, Close, and Help, below the groupboxes.</p>
    </div>

    <div class="note"><strong>The preview clears itself</strong> whenever you
    change parameter values, curve points/fit settings, or target values —
    rather than risk showing a plot that no longer matches your current
    settings. Press Compute Preview again to see the up-to-date result.</div>
    <p>The Preview tab itself has a few display controls, since a run of target
    values can easily number in the thousands and plotting/labeling all of
    them can get slow:</p>
    <ul>
        <li><strong>Original spectra</strong> / <strong>Generated spectra</strong>
            — two independent multi-select lists (click, or Ctrl/Shift-click
            for several, or the All/None buttons above each) — pick any
            combination of source and generated spectra to actually draw. Each
            selected spectrum, from either list, gets its own color and its
            own legend entry (source lines dashed, generated lines solid, so
            the two groups stay visually distinct even sharing the same color
            cycle). The legend itself can be dragged to reposition it if it's
            covering something you want to see.</li>
        <li><strong>Legend limit</strong> — caps how many of the SELECTED
            lines get their own legend entry, applied to each list
            independently (default 30 each). <strong>Show full legend</strong>
            lifts the cap for the current selection — can be slow if that's a
            lot of lines.</li>
    </ul>
    <div class="tip">A progress dialog appears while plotting large previews
    (over ~150 lines) — it's the drawing itself that's slow with many spectra,
    not computing them, so that's specifically what shows progress here, and
    it's skipped for small previews where it wouldn't be needed anyway.</div>

    <hr>
    <a href="#top">&#9650; back to top</a>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. It sits next to the
    <strong>Parameter name</strong> field at the top of the parameter
    values table (Step 1), and when checked applies everywhere this
    dialog shows a spectrum name: that table's Spectrum column, the
    Preview tab's Original/Generated spectra lists, and the preview
    plot's legend.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body>
    </html>
    """)

    return help_template.safe_substitute(images)
