# src/help/interactive_subtraction_help.py

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path


# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build — same mechanism as
# svd_interpolation_help.py / baseline_correction_help.py; see either for
# the full rationale.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "interactive_subtraction")

_SCREENSHOT_FILES = {
    "OVERVIEW":       "dialog_overview.png",
    "LISTS":          "minuend_subtrahend_lists.png",
    "FACTOR_SPEC":    "factor_specification.png",
    "COMMIT":         "commit_and_apply_buttons.png",
    "SHOW_INFO":      "show_info_dialog.png",
    "BATCH_SELECT":   "batch_selection.png",
    "XAXIS_MISMATCH": "xaxis_mismatch_dialog.png",
}

_SCREENSHOT_ALT = {
    "OVERVIEW":       "Interactive Subtraction dialog overview",
    "LISTS":          "Minuend list (blue), Preview combo box, All/Clear buttons, and Subtrahend list (red)",
    "FACTOR_SPEC":    "Subtraction factor slider, factor specification groupbox (Center, Half-width, number of points, Set as center), and Y axis limits for difference spectrum",
    "COMMIT":         "Update, Restore factor, Show info, Apply and Add as New buttons",
    "SHOW_INFO":      "Subtraction info dialog: a table of Minuend, Subtrahend, Factor rows with Select All and Remove Selected buttons",
    "BATCH_SELECT":   "Minuend list with several rows selected, plus the All and Clear buttons",
    "XAXIS_MISMATCH": "X-Axis Mismatch dialog with Align to Minuend X-Axis and Remove This Subtrahend buttons",
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


def get_interactive_subtraction_help_title():
    return "Interactive Spectrum Subtraction Help"

def get_interactive_subtraction_help_content():
    images = _resolve_screenshot_uris()
    # string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which
    # would collide with .format()-style placeholders — same reasoning as
    # svd_interpolation_help.py.
    help_template = Template("""
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2 { color: #1976D2; margin-top: 25px; }
            h3 { color: #F57C00; margin-top: 20px; }
            .tip { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .warning { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .important { background-color: #cce5ff; border: 1px solid #99ccff; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .formula { background-color: #e9ecef; padding: 8px; font-family: monospace; border-radius: 3px; margin: 8px 0; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
            ul { padding-left: 20px; }
            li { margin: 5px 0; }
        </style>
    </head>
    <body>
        <h1>Interactive Spectrum Subtraction Help</h1>

        <h2>Overview</h2>
        <p>Interactive spectrum subtraction removes the contribution of one spectrum (the
        <em>subtrahend</em>) from another (the <em>minuend</em>) by scaling the subtrahend
        with an adjustable factor and watching the result in real time. Typical uses:</p>
        <ul>
            <li>Removing solvent or buffer background</li>
            <li>Isolating a spectral component from a mixture</li>
            <li>Baseline correction using a reference spectrum</li>
            <li>Removing known interferents or contaminants</li>
        </ul>

        <p class="formula">Difference(x) = Minuend(x) &minus; Factor &times; Subtrahend(x)</p>

        <div class="screenshot">
            $OVERVIEW
            <p class="caption">The full dialog: component spectra / difference plots and slider on the left, Minuend / Subtrahend lists and commit controls on the right.</p>
        </div>

        <div class="important">
            <strong>One subtrahend per minuend.</strong> Each minuend has exactly one
            stored subtrahend/factor at a time &mdash; this models a single "subtract
            spectrum X from spectrum Y" relationship, not a chain of several. If you pick
            a different subtrahend for a minuend that already has one stored and click
            <strong>Update</strong>, the new choice <em>replaces</em> the old one rather
            than adding alongside it. If you genuinely need to remove several different
            contributions from the same sample, do it as separate, sequential
            subtractions: subtract the first, Apply, then reopen the dialog and subtract
            the next from the result.
        </div>

        <h2>Step-by-Step Usage</h2>

        <h3>Single Subtraction</h3>
        <ol>
            <li>Select at least two spectra in the main window.</li>
            <li>Choose <em>Interactive subtraction</em> from the Spectra Processing
                dropdown and click <strong>Parameters</strong>.</li>
            <li>In the <strong>Minuend</strong> list (blue highlight, right panel) click
                the spectrum you want to subtract <em>from</em>.</li>
            <li>In the <strong>Subtrahend</strong> list (red highlight) click the spectrum
                you want to subtract.</li>
            <li>An initial factor is estimated automatically via SVD and the slider is
                centred on it.</li>
            <li>Drag the <strong>slider</strong> to adjust the factor. Watch the difference
                spectrum (green, lower plot) &mdash; aim for a flat baseline with no
                residual subtrahend features.</li>
            <li>If you run out of slider range, increase <strong>Half-width</strong> or
                click <strong>Set as center</strong> to recentre on the current factor.</li>
            <li>Click <strong>Update</strong>. The operation summary label confirms
                exactly what will be stored.</li>
            <li>Click <strong>Apply</strong> (replace the minuend with the result) or
                <strong>Add as New</strong> (keep the original, add the result as a new
                spectrum) &mdash; both buttons are inside this dialog, right next to
                Update. There is no separate Run step in the main window for this
                operation.</li>
        </ol>

        <div class="screenshot">
            $COMMIT
            <p class="caption">The commit controls: Update stores the factor; Apply / Add as New (bottom) act on whatever is currently stored.</p>
        </div>

        <div class="important">
            <strong>Apply and Add as New ask for confirmation before committing</strong>
            &mdash; the same Yes/No prompt every Spectra Processing operation shows
            before its Apply / Add as New actually changes anything (see the
            <a href="help://developer_guide">developer guide</a>'s Apply / Add as New
            convention). It's worth calling out here specifically because it matters
            more in this dialog than in most:
            <ul>
                <li>Getting a good set of subtraction factors right &mdash; especially
                    across a whole batch of minuends &mdash; can take a while. A stray
                    click on Apply or Add as New partway through would commit whatever
                    happens to be stored so far, discarding the time spent tuning the
                    rest.</li>
                <li>Apply and Add as New sit directly next to <strong>Update</strong>,
                    which looks similar but does something completely different &mdash;
                    Update only stores a factor for later, it doesn't touch any spectra.
                    Early on, before the layout is familiar, it's easy to mean Update and
                    hit Apply instead. The confirmation catches exactly that slip.</li>
            </ul>
            Answering <strong>No</strong> (the default) leaves every stored factor
            untouched, exactly like clicking Close &mdash; nothing is lost, you're simply
            back at the dialog to keep working.
        </div>

        <h3>Batch Subtraction (same factor applied to many minuends)</h3>
        <p>The <strong>Minuend</strong> list always allows selecting more than one row
        &mdash; there is no separate mode to switch into first.</p>
        <ol>
            <li>Complete steps 1&ndash;7 above to find the right factor using one
                representative minuend. That spectrum's row is what the
                <strong>Preview</strong> combo box (just below the Minuend list) is
                currently showing &mdash; it always names whichever selected minuend is
                driving the slider and the plots.</li>
            <li>In the <strong>Minuend</strong> list, extend the selection to every
                spectrum you want to subtract from: Ctrl+click additional rows, or click
                <strong>All</strong> (just below the list) to select every available
                minuend at once. <strong>Clear</strong> deselects everything. The current
                subtrahend is automatically excluded from this list, since a spectrum
                cannot be subtracted from itself.</li>
            <li>Click <strong>Update</strong> &mdash; this stores the same subtrahend and
                factor for every currently-selected minuend (replacing any subtrahend
                already stored for each of them).</li>
            <li>Open <strong>Show info</strong> to verify all stored entries before
                committing.</li>
            <li>Click <strong>Apply</strong> or <strong>Add as New</strong>.</li>
        </ol>

        <div class="screenshot">
            $BATCH_SELECT
            <p class="caption">Several minuends selected at once (Ctrl+click, or the All button) — Update will store the same factor for every one of them.</p>
        </div>

        <div class="tip">
            <strong>Tip:</strong> The operation summary label below the Update button
            always shows the exact computation that Update will store, so you can
            verify minuend, subtrahend and factor before storing.
        </div>

        <h2>Dialog Layout</h2>

        <h3>Plot Area (left side)</h3>

        <h4>Upper Plot: Component Spectra</h4>
        <ul>
            <li><strong>Blue line (minuend):</strong> the spectrum you are subtracting from.</li>
            <li><strong>Red line (factor &times; subtrahend):</strong> the scaled subtrahend.</li>
        </ul>

        <h4>Lower Plot: Difference Spectrum</h4>
        <ul>
            <li><strong>Green line (difference):</strong> the result that Apply / Add as New
                will use.</li>
            <li>The x-axis zoom is preserved when you move the slider, so you can zoom
                into a region of interest and fine-tune without losing your view.</li>
        </ul>

        <h3>Subtraction Factor Slider &amp; Specification</h3>
        <p>The horizontal slider maps linearly between
        <em>center &minus; half-width</em> and <em>center + half-width</em>.
        The current factor is shown in blue to the right of the slider.</p>

        <div class="screenshot">
            $FACTOR_SPEC
            <p class="caption">The factor slider (top), the Subtraction factor specification groupbox (Center / Half-width / # of points / Set as center), and Y axis limits for difference spectrum, alongside each other.</p>
        </div>

        <ul>
            <li><strong>Center:</strong> midpoint of the slider range. Automatically set
                to the SVD estimate each time a new minuend or subtrahend is selected.</li>
            <li><strong>Half-width:</strong> distance from center to either end of the
                slider range. Increase for wider exploration; decrease for fine control.</li>
            <li><strong># of points:</strong> number of discrete slider steps (default
                1001). Higher values give finer resolution.</li>
            <li><strong>Set as center:</strong> moves Center to the current factor value,
                keeping Half-width unchanged. Use this when the slider is near an end and
                you want to continue adjusting further in the same direction.</li>
        </ul>

        <div class="tip">
            <strong>Example:</strong> SVD estimates 0.87. Center = 0.87, Half-width = 0.44
            gives a range of 0.43&ndash;1.31. If you need to go above 1.31, drag to the
            end, then click <em>Set as center</em> to recentre on the current value.
        </div>

        <h3>Y Axis Limits for Difference Spectrum</h3>
        <ul>
            <li><strong>Autoscale y:</strong> y-axis rescales automatically as you move
                the slider.</li>
            <li><strong>Rescale y:</strong> visible when Autoscale is off &mdash; manually
                fits the y-axis to current data.</li>
            <li><strong>Hide toolbar:</strong> toggles the matplotlib navigation toolbar.</li>
        </ul>

        <h3>Control Panel (right side)</h3>
        <ul>
            <li><strong>Restore factor:</strong> snaps the slider back to the stored
                factor for the current (minuend, subtrahend) pair, if one is stored.
                Useful after exploring with the slider and wanting to return to your
                approved value. Also triggered automatically when you switch between
                minuends or subtrahends.</li>
            <li><strong>Show info:</strong> displays a table of every stored
                (Minuend, Subtrahend, Factor) entry &mdash; one row per minuend, since
                each minuend can only have one stored subtrahend at a time. This is also
                where entries are removed: select one or more rows and click
                <strong>Remove Selected</strong>, or click <strong>Select All</strong>
                first to clear everything at once.</li>
            <li><strong>Help:</strong> opens this document.</li>
            <li><strong>Minuend list (blue):</strong> select one or more spectra &mdash;
                click for one, Ctrl+click/Shift+click to select several, or use the
                <strong>All</strong> / <strong>Clear</strong> buttons just below the list.
                Whichever of the selected rows is chosen in the <strong>Preview</strong>
                combo box (directly under the list) is the one shown/adjusted via the
                slider and plots; the others just sit selected, waiting for
                <strong>Update</strong>. The current subtrahend is left out of this list
                automatically &mdash; a spectrum cannot be subtracted from itself.</li>
            <li><strong>Subtrahend list (red):</strong> click to change the spectrum being
                subtracted. Changing the subtrahend re-estimates the factor via SVD (or
                restores a stored factor if one already exists for this exact pair).</li>
        </ul>

        <div class="screenshot">
            $LISTS
            <p class="caption">Minuend list (blue) with the Preview combo and All/Clear buttons below it, and the Subtrahend list (red).</p>
        </div>

        <h3>Update &mdash; Which Minuends It Applies To</h3>
        <p>There is no separate mode to switch into for batch use: the Minuend list
        above is always multi-select. <strong>Update</strong> stores the current
        subtrahend and factor for <em>every currently-selected row</em> in that list
        &mdash; one spectrum selected stores it for just that one; several selected
        (via Ctrl+click, Shift+click, or <strong>All</strong>) stores the same factor
        for all of them at once, replacing any subtrahend previously stored for each.</p>

        <h2>Removing Stored Factors</h2>
        <p>All removal happens from <strong>Show info</strong>, which shows exactly what's
        currently stored before you act on it:</p>
        <ul>
            <li>Select one or more rows (click, Ctrl+click, Shift+click) and click
                <strong>Remove Selected</strong> to delete just those.</li>
            <li>Click <strong>Select All</strong> first if you want to clear every stored
                factor in one action.</li>
        </ul>

        <div class="screenshot">
            $SHOW_INFO
            <p class="caption">Show info: every currently stored (Minuend, Subtrahend, Factor) entry, with Select All / Remove Selected for cleaning up.</p>
        </div>

        <h2>Factor Persistence</h2>
        <p>Stored factors are keyed by each spectrum's permanent internal identity, not by
        its display name. Consequences:</p>
        <ul>
            <li>Closing and reopening the dialog for the same spectra restores all
                previously stored factors automatically.</li>
            <li>Changing the main-window selection and switching back does <em>not</em>
                lose stored factors &mdash; they persist for the duration of the session.</li>
            <li>Renaming a minuend or subtrahend spectrum between storing a factor and
                applying it does not disconnect the stored factor from it &mdash; it's
                still found and shown under the spectrum's current name.</li>
            <li>Switching between minuends in the dialog automatically restores the stored
                factor for each pair, so you can review all subtractions without manually
                pressing Restore factor.</li>
            <li>If any factors are restored from an earlier session the moment the dialog
                opens, a one-line notice appears at the top of the right-hand panel saying
                how many &mdash; so it's clear those entries in Show info are carried over,
                not something left behind by mistake.</li>
        </ul>

        <h2>Automatic Factor Estimation (SVD)</h2>
        <p>When a new minuend/subtrahend pair has no stored factor, an initial estimate is
        computed automatically using Singular Value Decomposition:</p>
        <ol>
            <li>Minuend and subtrahend are arranged as the two columns of a matrix.</li>
            <li>SVD is applied: M = U&Sigma;V<sup>T</sup>.</li>
            <li>First principal component loadings V[:,0] are extracted.</li>
            <li>Factor = |V[0,0] / V[1,0]|.</li>
            <li>Center is set to this estimate; Half-width = max(0.5 &times; factor, 1.0).</li>
        </ol>
        <div class="tip">
            <strong>Tip:</strong> SVD estimation works best when the subtrahend is a
            dominant component of the minuend. For weak contributions, use the estimate as a
            starting point and refine visually.
        </div>

        <h2>Finding the Optimal Factor</h2>
        <ol>
            <li><strong>Start with the SVD estimate</strong> &mdash; it is usually close.</li>
            <li><strong>Watch the difference spectrum (green line):</strong>
                <ul>
                    <li>Residual subtrahend features visible &rarr; increase the factor.</li>
                    <li>Inverted features appear &rarr; decrease the factor
                        (over-subtraction).</li>
                    <li>Aim for the flattest, most featureless baseline in the
                        subtrahend region.</li>
                </ul>
            </li>
            <li><strong>Zoom into critical regions</strong> using the toolbar.</li>
            <li><strong>Check multiple spectral regions</strong> to ensure good subtraction
                across the entire range.</li>
            <li><strong>Adjust range as needed:</strong> increase Half-width for coarser
                exploration, decrease for fine-tuning.</li>
        </ol>

        <h3>Quality Control Checklist</h3>
        <ul>
            <li>&#10003; Difference spectrum has a flat baseline (no systematic trends).</li>
            <li>&#10003; No negative artifacts or inverted peaks (indicates over-subtraction).</li>
            <li>&#10003; No residual features from the subtrahend (under-subtraction).</li>
            <li>&#10003; The resulting spectrum makes physical/chemical sense.</li>
            <li>&#10003; Subtraction factor is physically reasonable (typically 0.1&ndash;10
                for concentration-matched measurements).</li>
        </ul>

        <h3>Common Pitfalls</h3>
        <ul>
            <li><strong>Over-subtraction:</strong> factor too high &rarr; negative peaks or
                inverted features. Reduce until they disappear.</li>
            <li><strong>Under-subtraction:</strong> factor too low &rarr; residual
                subtrahend features remain. Increase the factor.</li>
            <li><strong>Noise amplification:</strong> subtracting a very weak signal
                amplifies noise in the difference. Consider whether subtraction is
                appropriate for your data quality.</li>
            <li><strong>Spectral shift:</strong> small wavelength/wavenumber offsets between
                spectra create derivative-shaped artifacts. Correct alignment before
                subtraction if possible.</li>
            <li><strong>Non-linear relationships:</strong> this method assumes linear
                mixing. Inner filter effects, saturation, or non-linear detector response
                will degrade the result.</li>
            <li><strong>Trying to remove several contributions at once:</strong> storing a
                second subtrahend for a minuend that already has one replaces the first,
                it does not combine with it. If you need to remove more than one
                contribution from the same sample, do it as separate, sequential
                Apply steps (see the box near the top of this page).</li>
        </ul>

        <h2>Handling Different X-Scales</h2>
        <p>Subtraction is computed point-by-point, so the minuend and subtrahend must share
        an identical x-axis. If they don&rsquo;t, Interactive Subtraction refuses rather than
        interpolating for you &mdash; there is no preview, no auto-factor estimate, and Update
        will not store a factor for the pair.</p>
        <p>Spectra you select in the main window are already guaranteed to share one x-axis
        before this dialog opens. A mismatch can only happen with a subtrahend
        <strong>loaded from a file</strong> via &ldquo;Import subtrahend from file&rdquo;, since
        that file&rsquo;s axis is whatever the file contains. In that case you&rsquo;ll be
        offered a one-time choice:</p>
        <ul>
            <li><strong>Align to Minuend X-Axis:</strong> linearly interpolates the file-loaded
                subtrahend onto the minuend&rsquo;s x-axis, once, explicitly, for this dialog
                session only. Regions of the minuend&rsquo;s range outside the subtrahend&rsquo;s
                original range are filled with zero after alignment &mdash; check that this is
                what you want before relying on the result there.</li>
            <li><strong>Remove This Subtrahend:</strong> deletes it from the file-loaded
                subtrahend list for this session. An unaligned mismatched subtrahend can't be
                used for anything anyway, so there's no reason to keep it around asking about
                it again every time you select it. Re-import the file later if you want it
                back.</li>
        </ul>

        <div class="screenshot">
            $XAXIS_MISMATCH
            <p class="caption">The one-time X-Axis Mismatch prompt, shown only for a file-loaded subtrahend whose axis doesn't match the minuend.</p>
        </div>

        <div class="warning">
            <strong>Note:</strong> If your spectra come from different files or measurement
            sessions and don&rsquo;t line up, put them on a common axis with the Data Range
            operation first &mdash; that is the one place x-axis reconciliation happens
            openly, where you can see and check exactly what it did.
        </div>

        <h2>Workflow Integration</h2>

        <h3>Using with Other Operations</h3>
        <ul>
            <li>Subtraction is applied after all preceding operations in the pipeline
                (e.g., after normalization, smoothing, baseline correction).</li>
            <li>Can be followed by further operations (peak detection, peak fitting, etc.).</li>
            <li>Recorded in the Operations History &mdash; jump back to undo it, the same
                as any other processing step.</li>
            <li>Parameters are visible in the Operations Summary.</li>
        </ul>

        <h3>Typical Full Workflow</h3>
        <ol>
            <li>Import spectra including samples and reference/background.</li>
            <li>Apply preprocessing if needed (smoothing, normalization, data range).</li>
            <li>Select spectra for subtraction (at least 2), open Parameters.</li>
            <li>Find optimal factors for each minuend.</li>
            <li>Store with Update; verify with Show info.</li>
            <li>Click Apply or Add as New.</li>
            <li>Continue with further analysis.</li>
        </ol>

        <h3>Sequential Subtraction for Complex Mixtures</h3>
        <p>To remove more than one unwanted contribution from the same sample, do it as a
        sequence of separate subtractions rather than trying to store several subtrahends
        for one minuend at once:</p>
        <ol>
            <li>Subtract the dominant component first; click Apply.</li>
            <li>Reopen the dialog &mdash; the corrected spectrum is now available as a
                minuend in its own right.</li>
            <li>Subtract the next component from it; click Apply.</li>
            <li>Repeat until all unwanted contributions are removed.</li>
        </ol>

        <h3>Using with Normalized Spectra</h3>
        <ul>
            <li>The subtraction factor represents relative contribution in normalized units.</li>
            <li>Factors close to 1.0 indicate similar intensities.</li>
            <li>Factors much larger or smaller than 1.0 indicate different concentration
                or intensity levels between the two spectra.</li>
        </ul>

        <h2>Troubleshooting</h2>

        <h3>Dialog won&rsquo;t open</h3>
        <p>Select at least 2 spectra in the main window before clicking Parameters.</p>

        <h3>Slider not responding</h3>
        <p>Check that Half-width is greater than zero. If Center and Half-width produce
        identical limits the slider has no range.</p>

        <h3>Cannot find a good subtraction factor</h3>
        <ul>
            <li>The subtrahend may not be a component of the minuend.</li>
            <li>Spectra have different baselines &mdash; apply baseline correction first.</li>
            <li>X-scales do not overlap sufficiently.</li>
            <li>The relationship is non-linear (inner filter effect, saturation, etc.).</li>
        </ul>

        <h3>Result after Apply doesn&rsquo;t match the dialog preview</h3>
        <p>You must click <strong>Update</strong> before clicking Apply or Add as New.
        Moving the slider alone does not store the factor &mdash; Update is the explicit
        commit-to-storage step; Apply / Add as New then act on whatever Show info
        currently lists.</p>

        <h3>I stored a factor for a different subtrahend and the old one disappeared</h3>
        <p>This is expected: each minuend keeps only one stored subtrahend at a time, so
        storing a new one for the same minuend replaces the previous choice. If you want
        to remove several different contributions from one sample, see
        <em>Sequential Subtraction for Complex Mixtures</em> above instead of trying to
        keep multiple subtrahends stored for the same minuend.</p>

        <h3>Plot doesn&rsquo;t fill window after Home click</h3>
        <p>Move the slider slightly after clicking Home to trigger a redraw. The plot will
        rescale correctly.</p>

        <h2>Examples</h2>

        <h3>Example 1: Buffer/Solvent Subtraction</h3>
        <p><strong>Scenario:</strong> Protein sample measured in buffer; remove buffer contribution.</p>
        <ol>
            <li>Import sample+buffer and pure buffer spectra.</li>
            <li>Set sample+buffer as minuend, pure buffer as subtrahend.</li>
            <li>Adjust slider until buffer features disappear from the difference.</li>
            <li>Click Update, then Apply.</li>
        </ol>
        <p><strong>Expected result:</strong> Pure protein spectrum without buffer contributions.</p>

        <h3>Example 2: Component Isolation</h3>
        <p><strong>Scenario:</strong> Binary mixture; isolate component A by removing component B.</p>
        <ol>
            <li>Set mixture as minuend, pure component B as subtrahend.</li>
            <li>Adjust factor until all component B features vanish from the difference.</li>
            <li>The green difference spectrum shows isolated component A.</li>
            <li>Update, then Apply.</li>
        </ol>
        <p><strong>Expected result:</strong> Isolated component A spectrum.</p>

        <h3>Example 3: Batch Background Subtraction</h3>
        <p><strong>Scenario:</strong> Ten samples all measured in the same buffer.</p>
        <ol>
            <li>Select all 10 samples plus the buffer spectrum.</li>
            <li>Find the optimal factor for one representative sample.</li>
            <li>Click <strong>All</strong> below the Minuend list to select all 10 samples
                at once (the buffer itself, as the current subtrahend, is automatically
                excluded from the list).</li>
            <li>Click Update to apply the same factor to all 10.</li>
            <li>Open Show info to verify all 10 entries.</li>
            <li>Click Apply or Add as New.</li>
        </ol>
        <p><strong>Expected result:</strong> All 10 samples with buffer contribution removed.</p>

        <h3>Example 4: Baseline Subtraction</h3>
        <p><strong>Scenario:</strong> Sample with sloping baseline; you have a reference baseline.</p>
        <ol>
            <li>Set sample as minuend, baseline reference as subtrahend.</li>
            <li>Adjust factor until the difference spectrum has a flat baseline.</li>
            <li>A factor close to 1.0 indicates the reference is well-matched.</li>
        </ol>
        <p><strong>Expected result:</strong> Sample spectrum with corrected baseline.</p>

        <h2>Summary</h2>
        <p>Key features of Interactive Spectrum Subtraction:</p>
        <ul>
            <li>Real-time visual feedback with two synchronized plots.</li>
            <li>Automatic initial factor estimation using SVD.</li>
            <li>Center/Half-width slider range &mdash; predictable, no runaway values.</li>
            <li>One stored subtrahend per minuend, tied to the spectrum's permanent
                identity &mdash; survives renaming and dialog close/reopen.</li>
            <li>Automatic factor restoration when switching between minuend spectra.</li>
            <li>Batch processing: select several minuends at once in the same
                always-multi-select Minuend list (Ctrl+click, or the All button).</li>
            <li>Apply / Add as New committed directly from this dialog &mdash; no separate
                Run step.</li>
            <li>Operation summary label shows exactly what will be stored.</li>
            <li>Full integration with the operations pipeline (history, undo, summary).</li>
        </ul>

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
