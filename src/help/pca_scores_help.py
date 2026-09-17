# src/help/pca_scores_help.py

"""
Help content for PCA / SVD Scores & Loadings functionality.
This module contains detailed help information that can be reused across the application.
"""

import os
import struct
from pathlib import Path
from string import Template

# NOTE: adjust this import to match wherever resource_path() actually lives
# in your project.
from src.modules.utils.resource_path import resource_path


# Screenshots referenced by this help page live in their own subfolder so
# names don't collide with other help topics' screenshots sharing the same
# parent resources/images/help_screenshots/ directory.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "pca_scores")

_SCREENSHOT_FILES = {
    "OVERVIEW":             "dialog_overview.png",
    "SVD_SETTINGS":         "svd_settings_group.png",
    "METRIC_DISPLAY":       "metric_display_group.png",
    "SCORES_PLOT_GROUP":    "scores_plot_group.png",
    "SCORES_3D":            "scores_3d_plot.png",
    "SCORES_HOTELLING":     "scores_colour_hotelling.png",
    "LOADINGS_PLOT_GROUP":  "loadings_plot_group.png",
    "LOADINGS_EXAMPLE":     "loadings_tab_example.png",
    "VARIANCE_SINGLE":      "variance_single_metric.png",
    "VARIANCE_COMPARE":     "variance_compare_metrics.png",
    "VARIANCE_OVERVIEW":    "variance_overview_all.png",
    "VARIANCE_TABLE":       "metrics_table.png",
    "SAVE_DIALOG":          "save_dialog.png",
}

# Cap displayed screenshot width at this many pixels — see
# svd_reconstruction_help.py / data_range_help.py for why explicit
# width/height attributes are used instead of relying on CSS to constrain
# image size.
_MAX_IMG_WIDTH = 700


def _png_size(path):
    """Return (width, height) in pixels for a PNG, read from its IHDR chunk."""
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
    preserved) so every <img> tag renders at a sane, consistent size.
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
            display_w, display_h = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)

        values[f"{key}_W"] = str(display_w)
        values[f"{key}_H"] = str(display_h)

    return values


def get_pca_scores_help_title():
    """Return the title for PCA scores & loadings help."""
    return "PCA / SVD — Scores & Loadings — Help"


def get_pca_scores_help_content():
    """
    Get the HTML help content for PCA / SVD Scores & Loadings.

    Returns:
        str: HTML formatted help content
    """
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders), not str.format()/f-strings — the
    # CSS block below is full of literal { } braces that would collide with
    # .format()-style placeholders.
    help_template = Template("""
    <html><head><style>
        body  { font-family:Arial,sans-serif; margin:20px; line-height:1.6; font-size:13px; }
        h1    { color:#2E7D32; border-bottom:2px solid #2E7D32; }
        h2    { color:#1565C0; margin-top:22px; }
        h3    { color:#E65100; margin-top:14px; margin-bottom:4px; }
        .tip  { background:#E8F5E9; border-left:4px solid #2E7D32; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .note { background:#E3F2FD; border-left:4px solid #1565C0; padding:10px 14px; border-radius:3px; margin:8px 0; }
        table { border-collapse:collapse; width:100%; margin:8px 0; }
        th    { background:#E3F2FD; text-align:left; padding:6px 8px; }
        td    { border-bottom:1px solid #e0e0e0; padding:5px 8px; vertical-align:top; }
        ul,ol { padding-left:20px; } li { margin:3px 0; }
        hr    { border:none; border-top:1px solid #ddd; margin:20px 0; }
        .fm   { font-family:monospace; background:#ececec; padding:1px 5px; border-radius:3px; }
        .screenshot { margin: 12px 0; text-align: center; }
        .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
        .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
    </style></head><body>

    <h1>PCA / SVD — Scores &amp; Loadings</h1>

    <p>Visualises the results of Singular Value Decomposition (SVD) — the same
    decomposition used by the SVD Background Correction tool — as PCA-style
    scores and loadings plots. No separate computation is needed; the SVD is
    recomputed from the selected spectra on demand.</p>

    <div class="screenshot">
        <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="PCA Scores and Loadings dialog overview" />
        <p class="caption">The full dialog: SVD settings, Metric display, and the active tab's plot-settings group on the left; the Scores/Loadings/Diagnostics tabs and canvas on the right.</p>
    </div>

    <div class="note">
        <strong>SVD and PCA:</strong> for mean-centred data, SVD and PCA are
        equivalent — which is why this dialog's <strong>Mean-center
        spectra before SVD</strong> checkbox (in SVD settings, below) is
        <strong>checked by default</strong>: with it on, this really is
        textbook PCA. The components are ordered by decreasing explained
        variance (singular value squared / total) either way.
    </div>

    <div class="note">
        <strong>Why mean-centering matters:</strong> absorbance data is
        never zero-mean (it's always positive), so an <em>uncentered</em>
        first component is usually dominated by whatever signal level
        every selected spectrum shares in common — closer to "the average
        spectrum" than to how your spectra actually differ from each
        other. Verified directly on real data: an uncentered PC1's
        per-spectrum trajectory correlated &gt;0.96 with the plain
        per-point mean, while mean-centered PC1 correlated &gt;0.98 with
        the <em>uncentered</em> PC2 — i.e. centering isolates the same
        real variation that would otherwise be split across two
        uncentered components instead of concentrated in one. Leave it
        checked unless you specifically want to compare against
        SVD Analysis's traditional uncentered convention (that dialog
        defaults the same checkbox off, for exactly that reason).
        Toggling it recomputes instantly.
    </div>

    <div class="note">
        <strong>This dialog vs. SVD Analysis — which one to use:</strong> both
        decompose the same data with the same underlying SVD; they just present
        it for different questions.
        <ul>
            <li><strong>Use this dialog (Scores &amp; Loadings)</strong> when your
                question is about <em>samples</em> or <em>variables</em>
                separately: "do my spectra cluster into groups?", "which one is an
                outlier?", "which wavenumbers drive that separation?" Scores
                (sample relationships) and Loadings (variable relationships) are
                shown as separate, full-size tabs because they're usually
                examined independently, at different points in an analysis — this
                is the standard convention in chemometrics software (SIMCA,
                PLS_Toolbox, Unscrambler all do the same).</li>
            <li><strong>Use <a href="help://svd_analysis">SVD Analysis</a></strong> when your question is about one
                <em>component</em> at a time: "what does component 3 actually look
                like, and how strongly does it show up across my samples?" There,
                a component's shape (subspectrum) and its strength per sample
                (coefficients) are two views of the <em>same</em> object, so they're
                shown paired, side by side — and that dialog adds reconstruction
                tools (rebuild spectra from N components) and richer diagnostics
                (Malinowski IND, residual error) for deciding how many components
                are real signal.</li>
        </ul>
        In short: scores/loadings for sample- and variable-level questions;
        SVD Analysis for component-by-component inspection and reconstruction.
    </div>

    <p>The left panel starts with the <strong>SVD settings</strong> group: a
    <strong>Max components</strong> spinbox and <strong>Recompute SVD</strong>
    button for choosing how many components to compute and re-running the
    decomposition after changing it, plus the <strong>Mean-center spectra
    before SVD</strong> checkbox described above (checked by default).
    Unlike the component count, toggling mean-centering recomputes
    immediately on its own — it changes the whole decomposition, not just
    how many components are kept, so there's no "stale until you click
    Recompute" state to leave you looking at results from the setting
    you just changed away from.</p>

    <div class="screenshot">
        <img src="$SVD_SETTINGS" width="$SVD_SETTINGS_W" height="$SVD_SETTINGS_H" alt="SVD settings group with Mean-center checkbox, Max components spinbox, and Recompute SVD button" />
        <p class="caption">The SVD settings group: the Mean-center checkbox, Max components spinbox, and the "Recompute SVD" button.</p>
    </div>

    <div class="tip">
        <strong>Settings follow the active tab:</strong> the Scores plot and
        Loadings plot settings groups in the left panel only show up when their
        matching tab is the one currently selected on the right — switching tabs
        automatically shows the relevant settings and hides the other group,
        rather than showing both at once regardless of which one applies.
    </div>

    <div class="note">
        <strong>Metric display</strong> (always visible, just below SVD settings)
        controls one shared choice used in two places: the number shown next to
        each PC in Scores axis labels, and in the Loadings component list.
        <ul>
            <li><strong>Metric:</strong> any of the seven metrics described in the
                Diagnostics tab section below (defaults to Explained variance (%)).</li>
            <li><strong>Format:</strong> Fixed (e.g. 0.029) or Scientific
                (e.g. 2.9e-02). Some components — especially higher-order ones —
                can have a vanishingly small share that rounds to 0.0% at low
                precision, which looks broken even though the real number is fine.</li>
            <li><strong>Decimals:</strong> how many digits to show (default 3).</li>
        </ul>
    </div>

    <div class="screenshot">
        <img src="$METRIC_DISPLAY" width="$METRIC_DISPLAY_W" height="$METRIC_DISPLAY_H" alt="Metric display group with Metric, Format, and Decimals controls" />
        <p class="caption">The Metric display group: Metric, Format (Fixed or Scientific), and Decimals — always visible, just below SVD settings.</p>
    </div>

    <p>At the very bottom of the left panel sit <strong>Save&hellip;</strong>,
    <strong>Help</strong>, and <strong>Close</strong> — these three stay in
    place no matter which tab is active.</p>

    <hr>
    <h2>Scores tab</h2>
    <p>Each point represents one spectrum projected onto two (or three, in 3D
    mode) principal components.
    Spectra that are similar to each other cluster together; outliers appear
    separated from the main group. The axis range is fit to the actual data
    (not stretched out to include the zero-reference lines, which are drawn
    for orientation but won't expand the view if the data sits well away from
    the origin).</p>

    <div class="screenshot">
        <img src="$SCORES_PLOT_GROUP" width="$SCORES_PLOT_GROUP_W" height="$SCORES_PLOT_GROUP_H" alt="Scores plot group with X axis, Y axis, Z axis, 3D plot checkbox, Colour by combo, and Show labels checkbox" />
        <p class="caption">The Scores plot group: X axis / Y axis (/ Z axis) PC selectors, the "3D plot" checkbox, "Colour by", and "Show labels".</p>
    </div>

    <ul>
        <li><strong>X axis / Y axis:</strong> choose which PC pair to plot
            (default PC1 vs PC2).</li>
        <li><strong>3D plot:</strong> adds a Z axis and a third PC selector,
            turning the scatter into a rotatable 3D plot. Sometimes reveals
            separation between groups that overlap in any single 2D
            projection. Needs at least 3 computed components — automatically
            turns itself off if you reduce <em>Max components</em> below 3.</li>
        <li><strong>Colour by index:</strong> spectra coloured sequentially
            by their position — useful for spotting drift over time.</li>
        <li><strong>Colour by PC1, PC2, ...:</strong> maps that component's
            score onto the point colour, giving a pseudo-3D view without
            needing the 3D toggle. The list always matches however many
            components are actually computed (rebuilt after every SVD
            computation) — it's a different choice from whichever PCs are
            currently on the X/Y/Z axes, so colouring by a third (or
            fourth, fifth, ...) component adds genuinely new information.</li>
        <li><strong>Colour by T&sup2; (Hotelling):</strong> a standard PCA
            outlier-detection statistic — see below.</li>
        <li><strong>Show labels:</strong> annotates each point with the last
            20 characters of the spectrum label.</li>
    </ul>

    <div class="screenshot">
        <img src="$SCORES_3D" width="$SCORES_3D_W" height="$SCORES_3D_H" alt="3D scores scatter plot with a third principal component axis" />
        <p class="caption">A 3D scores plot: rotatable in the app, useful when two groups overlap in every 2D pair you've tried.</p>
    </div>

    <div class="note">
        <strong>Hotelling's T&sup2;:</strong> combines all the components
        currently plotted (X, Y, and Z if 3D is on) into a single per-spectrum
        score — each component's scores are standardized, squared, and summed.
        Spectra that sit far from the bulk of the data in <em>any</em> of those
        components get a high T&sup2;, making this a quick way to flag unusual
        spectra without inspecting each component pair separately. It changes
        if you change which PCs are plotted, since it's computed only from
        those.

        <div class="screenshot">
            <img src="$SCORES_HOTELLING" width="$SCORES_HOTELLING_W" height="$SCORES_HOTELLING_H" alt="Scores plot coloured by Hotelling's T-squared, highlighting an outlier spectrum" />
            <p class="caption">Scores coloured by T&sup2; (Hotelling) — points with a noticeably higher value stand out as outlier candidates.</p>
        </div>
    </div>

    <p>Use the <strong>Save…</strong> button (bottom of the left panel) to save
    scores to Excel or text/CSV — see Saving data below.</p>

    <hr>
    <h2>Loadings tab</h2>
    <p>Each loading is a spectrum-shaped vector showing which wavenumber regions
    contribute most to that component. The x-axis is scaled to fit the actual
    data range. Each curve's legend label shows the same metric currently chosen
    in Metric display (above) — change it there and both the component list and
    this legend update together.</p>

    <div class="note">
        With <strong>Mean-center</strong> checked (the default), a loading
        describes how spectra <em>deviate</em> from the mean spectrum, not
        an absolute spectral shape — component 1 is "the main way spectra
        differ from average," not "what a typical spectrum looks like."
        With it unchecked, component 1 usually looks much more like a
        typical raw spectrum, since nothing has been subtracted out.
        Neither is "more correct" than the other, but they answer
        different questions — bear this in mind when interpreting band
        shapes.
    </div>

    <div class="screenshot">
        <img src="$LOADINGS_PLOT_GROUP" width="$LOADINGS_PLOT_GROUP_W" height="$LOADINGS_PLOT_GROUP_H" alt="Loadings plot group: component list with a ? help button and the Offset for clarity checkbox" />
        <p class="caption">The Loadings plot group: the component list (Ctrl+click / Shift+click to select several), the "?" quick-reminder button, and "Offset for clarity".</p>
    </div>

    <ul>
        <li>Positive loading regions push a spectrum&apos;s score positive;
            negative regions push it negative.</li>
        <li><strong>Offset for clarity:</strong> shifts each loading vertically
            so overlapping curves are readable.</li>
        <li>Select multiple components with Ctrl+click (add/remove
            individually) or Shift+click (select a range) — click the small
            <strong>?</strong> button next to the component list for a quick
            reminder.</li>
    </ul>

    <div class="screenshot">
        <img src="$LOADINGS_EXAMPLE" width="$LOADINGS_EXAMPLE_W" height="$LOADINGS_EXAMPLE_H" alt="Loadings tab showing several offset, overlaid loading curves" />
        <p class="caption">Several loadings shown together with "Offset for clarity" enabled, so overlapping curves stay readable.</p>
    </div>

    <div class="tip">
        <strong>Interpreting loadings:</strong> if PC1 loading has a peak at
        1004&nbsp;cm&sup1; (phenylalanine), then PC1 separates spectra primarily
        by their phenylalanine content.
    </div>
    <p>Use the <strong>Save…</strong> button to save loadings to Excel or
    text/CSV — see Saving data below.</p>

    <hr>
    <h2>Diagnostics tab</h2>
    <p>Seven metrics, all derived from the same SVD, presented the same way and
    using the same names as SVD Analysis's own Diagnostics tab. Three view modes:</p>
    <ul>
        <li><strong>Single metric</strong> — plot any one metric vs component
            number, with a "Log scale" checkbox that resets to that metric's
            own recommended default (log for &sigma;, Eigenvalue, Residual
            error, and Malinowski IND; linear for the three variance-percentage
            metrics) whenever you change metric, but can be overridden either
            way.</li>
        <li><strong>Compare two metrics</strong> — two panels side by side,
            each plotting one metric against component number (the same
            layout as SVD Analysis), rather than one metric scattered against
            the other. This answers "do these two metrics agree on which
            component the signal-to-noise boundary falls at?", which needs
            both plotted against the same shared x-axis (component number) —
            a dashed line marks the Malinowski IND minimum on both panels so
            you can see how it lines up with whatever else you're comparing.
            Each panel has its own independent "Log X" / "Log Y" checkbox,
            each defaulting to that panel's own metric. The info button reads
            "What does this comparison mean?" in this mode and explains the
            <em>relationship</em> between the two curves — what to look for
            when they agree, and what it means when they don't — not just
            each metric's own definition restated.</li>
        <li><strong>Overview (all)</strong> — fixed 2&times;4 grid showing
            all seven metrics at once (one cell unused), each using its own
            metric's default scale unless "Log scale (overview)" is checked,
            which forces log scale on every panel.</li>
    </ul>

    <div class="screenshot">
        <img src="$VARIANCE_SINGLE" width="$VARIANCE_SINGLE_W" height="$VARIANCE_SINGLE_H" alt="Diagnostics tab Single metric view with the What does this metric mean button" />
        <p class="caption">"Single metric" view mode, with the "ℹ What does this metric mean?" button.</p>
    </div>

    <div class="screenshot">
        <img src="$VARIANCE_COMPARE" width="$VARIANCE_COMPARE_W" height="$VARIANCE_COMPARE_H" alt="Diagnostics tab Compare two metrics view showing two side by side panels against component number" />
        <p class="caption">"Compare two metrics" view mode: two panels side by side, each metric plotted against component number, with the Malinowski IND minimum marked on both.</p>
    </div>

    <div class="screenshot">
        <img src="$VARIANCE_OVERVIEW" width="$VARIANCE_OVERVIEW_W" height="$VARIANCE_OVERVIEW_H" alt="Diagnostics tab in Overview (all) mode showing all seven metrics in a grid" />
        <p class="caption">"Overview (all)" mode: all seven metrics shown at once in a 2×4 grid (one cell unused).</p>
    </div>

    <table>
        <tr><th>Metric</th><th>Meaning</th></tr>
        <tr><td><strong>Singular values (&sigma;)</strong></td><td>From
            X = U &times; diag(&sigma;) &times; V&#7488;. Look for a kink where
            the steep drop flattens — that marks the signal-to-noise
            boundary.</td></tr>
        <tr><td><strong>Eigenvalue (&sigma;&sup2;)</strong></td><td>Singular
            value squared — the absolute amount of variance that component
            accounts for, before converting to a percentage. For raw,
            unnormalized spectral intensities, eigenvalues commonly reach
            1e8–1e16 or beyond — this is expected, not a sign of a problem.
            It scales with the square of the data's absolute intensity scale,
            so it carries no inherent "normal" range; only its relative size
            across components matters.</td></tr>
        <tr><td><strong>Explained variance (%)</strong></td><td>Eigenvalue as a
            percentage of the total.</td></tr>
        <tr><td><strong>Cumulative explained var. (%)</strong></td><td>Running
            total of explained variance using the first N components.</td></tr>
        <tr><td><strong>Cumulative unexplained var. (%)</strong></td><td>100%
            minus cumulative explained variance — how much information is lost
            by truncating at N components.</td></tr>
        <tr><td><strong>Residual error E(m)</strong></td><td>Residual standard
            deviation if only the first <em>m</em> components are kept (same
            formula used by SVD Background's own diagnostics). Has no value
            for the very last component (nothing left over to measure
            residual against). Decreases monotonically — useful, but has no
            true minimum on its own.</td></tr>
        <tr><td><strong>Malinowski IND</strong></td><td>Residual error
            divided by (number of spectra &minus; components retained)&sup2;.
            This normalization makes IND turn back upward once you've
            retained more components than there are real factors, giving it
            an actual minimum — more reliable than Residual error alone for
            pinpointing the optimal count. Most reliable when the number of
            data points per spectrum greatly exceeds the number of spectra;
            for large or near-square datasets the minimum can be
            unreliable.</td></tr>
    </table>
    <div class="tip">
        <strong>Using Residual error / IND to pick a component count:</strong>
        Residual error typically decreases as you retain more components,
        then flattens out once you're only adding noise — the point where it
        stops decreasing meaningfully is a rough guide. <strong>Malinowski
        IND</strong> is the more reliable of the two for this purpose: look
        for its <em>minimum</em> — that component count is the statistically
        suggested cutoff. Treat both as a complementary check alongside the
        "elbow" in the cumulative variance curve, not a replacement for
        visual inspection of the loadings themselves.
    </div>
    <ul>
        <li><strong>Log scale</strong> — several metrics span orders of
            magnitude; a log scale makes the elbow/cutoff point far easier
            to see than a linear scale, which compresses everything past the
            first few components into an unreadable flat line. Single metric
            mode has one checkbox that resets to the selected metric's own
            default whenever you change metric; Compare mode has one per
            panel; Overview mode has a single "force log on everything"
            checkbox, since seven independent per-panel checkboxes in a grid
            that small would be more clutter than it's worth.</li>
        <li><strong>&#8505; What does this metric mean? / What does this
            comparison mean?</strong> — the button's label and content follow
            the current view mode: in Single metric mode it explains the
            selected metric; in Compare mode it explains how to read the
            <em>relationship</em> between the two selected metrics (specific
            guidance for common pairs, e.g. &sigma; vs Malinowski IND, with a
            general explanation for less common pairings); it's disabled in
            Overview mode, where seven metrics at once don't reduce to a
            single explanation.</li>
        <li><strong>Show all metrics (table)&hellip;</strong> — opens every
            metric, for every component, as one table in a larger window —
            easier to scan precisely than reading values off a plot. Has its
            own Export&hellip; button for a quick CSV of just this table.</li>
    </ul>

    <div class="screenshot">
        <img src="$VARIANCE_TABLE" width="$VARIANCE_TABLE_W" height="$VARIANCE_TABLE_H" alt="All metrics table window listing all seven metrics for every component, with Export and Close buttons" />
        <p class="caption">The "Show all metrics (table)…" window: every metric for every component in one table, with its own Export… and Close buttons.</p>
    </div>

    <hr>
    <h2>Saving data</h2>
    <p>The <strong>Save…</strong> button (bottom of the left panel) opens a
    dialog with the same shape as SVD Analysis's Save&hellip;:</p>

    <div class="screenshot">
        <img src="$SAVE_DIALOG" width="$SAVE_DIALOG_W" height="$SAVE_DIALOG_H" alt="Save dialog with File Format, Include (Scores, Loadings, Variance), and Output File groups" />
        <p class="caption">The Save… dialog: File Format (Excel or Text/CSV), the Include section (Scores / Loadings / Variance (metrics)), and the Output File path with Browse….</p>
    </div>

    <ul>
        <li><strong>File Format:</strong> Excel (.xlsx) or Text/CSV.</li>
        <li><strong>Include:</strong> Scores, Loadings, and/or Variance
            metrics — tick any combination; all three are included by
            default.</li>
        <li>For Excel, each included category becomes its own worksheet
            (Scores / Loadings / Variance), with columns automatically
            widened so headers are fully visible the moment the file opens.</li>
        <li>For Text/CSV, choose a delimiter and decimal precision, and
            whether to combine everything into one file or write a separate
            file per category.</li>
    </ul>
    <p>This is separate from the <strong>save icon</strong> in each plot's
    toolbar, which exports the <em>image</em> of the current plot (PNG, PDF,
    SVG) rather than the underlying numbers.</p>

    <div class="note">
    <strong>Scores are unit-normalized.</strong> The exported Scores
    (PC1, PC2, &hellip;) have unit length &mdash; they are <em>not</em>
    multiplied by the singular value. This is a legitimate, common SVD
    convention, but it differs from scikit-learn's <code>PCA.transform()</code>
    or the classical (Jolliffe) statistics definition of a PCA score, which
    <em>is</em> scaled by the singular value (equivalently, by
    &radic;eigenvalue). If you need that convention &mdash; for example, to
    compare directly against another tool's output &mdash; multiply each
    exported PCk column by its matching value in the Variance sheet's
    Singular_values column.
    </div>

    <hr>
    <h2>Practical tips</h2>
    <ul>
        <li><strong>Pre-process first.</strong> Apply baseline correction and
            normalisation before running PCA. Unprocessed spectra with large
            fluorescence backgrounds will have PC1 dominated by the background,
            not by the spectral features of interest.</li>
        <li><strong>Use Data range</strong> to restrict the x-axis to the
            fingerprint region before running PCA — this removes noise-dominated
            regions from the decomposition.</li>
        <li>Increase <strong>Max components</strong> and re-run SVD to see
            higher-order components. Components beyond the elbow are dominated
            by noise.</li>
        <li><strong>Finding outliers:</strong> switch Colour by to
            <strong>T&sup2; (Hotelling)</strong> and look for points with
            noticeably higher values than the rest — these are candidates for
            closer inspection (contamination, instrument glitches, mislabelled
            samples) rather than necessarily being removed outright.</li>
        <li><strong>3D plots</strong> are most useful when two groups overlap
            in every 2D pair you've tried — adding a third component
            sometimes separates them, at the cost of being harder to read on
            a static screenshot (rotate it interactively instead).</li>
    </ul>

    <hr>
    <h2 id="technical-background">Technical background: centering, orthonormality, and why SVD = PCA</h2>

    <div class="note">
        <strong>"Normalized" means two different things here — don't
        conflate them.</strong>
        <ol>
            <li><strong>Orthonormal components</strong> (unit length, at
                right angles to each other) — this is a built-in property
                of SVD itself. Every U column and every V column always
                has length exactly 1 and is exactly orthogonal to every
                other column, whether or not the input data was centered
                or scaled. Nothing about the data needs to be
                "normalized" first for this — it falls straight out of
                the SVD algorithm, unconditionally.</li>
            <li><strong>Standardizing/scaling the data</strong> (dividing
                each wavelength's values by its own standard deviation
                before decomposing) — a separate, optional preprocessing
                choice, unrelated to point 1. This is what turns
                covariance-based PCA into correlation-based PCA. It's the
                <em>data</em> being rescaled, not the resulting components
                (which are orthonormal either way).</li>
        </ol>
        This dialog's Mean-center checkbox is about centering only
        (subtracting the mean spectrum) — it does not standardize/scale
        wavelength channels, and deliberately doesn't offer to: see below
        for why. To get the centered spectra themselves as new spectra in
        your list — without running any decomposition — see the standalone
        <a href="help://mean_centering">Mean-Center Spectra (Dataset)</a>
        operation (Axis &amp; Unit Conversion menu), which performs this
        exact same centering step.
    </div>

    <div class="note">
        <strong>Why centering alone makes SVD exactly equal to PCA (no
        scaling required):</strong> for a centered data matrix
        <span class="fm">X<sub>c</sub></span>, its SVD
        (<span class="fm">X<sub>c</sub> = U&middot;diag(s)&middot;V<sup>T</sup></span>)
        and the eigendecomposition of its covariance matrix
        (<span class="fm">X<sub>c</sub>X<sub>c</sub><sup>T</sup>/(n-1)</span>)
        are the same computation viewed two ways: U's columns are exactly
        the covariance matrix's eigenvectors, and
        <span class="fm">s&sup2;/(n-1)</span> exactly equals its
        eigenvalues. Verified directly: computing both ways on the same
        centered data gave eigenvector/loading correlation of 1.000 and
        eigenvalues matching <span class="fm">s&sup2;/(n-1)</span> to
        full displayed precision. No standardization step is needed for
        that equivalence — it's a property of centering by itself.
    </div>

    <div class="note">
        <strong>Why this dialog doesn't offer to standardize wavelength
        channels too:</strong> standardizing forces every channel to unit
        variance, which erases exactly the information SVD/PCA uses to
        decide what's signal and what's noise. Checked directly on the
        3-transition demo dataset: a flat, uninformative baseline
        wavelength had std&nbsp;&asymp;&nbsp;0.036, while a real
        transition band had std&nbsp;&asymp;&nbsp;0.199 — SVD naturally
        gives the real band about 5.6&times; more weight than the flat
        region, which is exactly the behavior you want. Standardizing
        first would force both regions to contribute equally, amplifying
        whatever noise lives in the flat region up to the same importance
        as genuine signal. (Standardizing makes more sense when combining
        variables measured in genuinely different, incomparable units —
        e.g. age in years alongside income in dollars — which isn't the
        situation here: every wavelength channel is already the same
        physical quantity on the same scale.)
    </div>

    <div class="note">
        <strong>Why mean-centered components are uncorrelated, not just
        orthogonal — a short proof, not just a numerical observation:</strong>
        centering subtracts each wavelength's own mean <em>across
        spectra</em>, so every row of <span class="fm">X<sub>c</sub></span>
        sums to zero across the spectra it contains — equivalently,
        <span class="fm">X<sub>c</sub>&middot;<strong>1</strong> = <strong>0</strong></span>,
        where <strong>1</strong> is the all-ones vector in spectrum-space.
        That puts <strong>1</strong> in <span class="fm">X<sub>c</sub></span>'s
        null space. By the fundamental theorem of linear algebra, a
        matrix's row space is orthogonal to its null space — and every
        component's score vector (how strongly it shows up across your
        spectra) lives in that row space. So every score vector must be
        orthogonal to <strong>1</strong>, which is exactly what
        "zero-mean" means for a vector. Zero-mean <em>and</em> orthogonal
        (SVD already guarantees the orthogonal part) is precisely the
        condition for zero Pearson correlation — correlation is just a
        normalized dot product between mean-subtracted vectors. Verified
        directly: every real (non-degenerate) component's score vector
        had mean &asymp; 1&times;10<sup>-17</sup> (floating-point zero),
        and cross-component correlations across several arbitrary pairs
        all landed at the same floating-point zero — while the identical
        check on <em>un</em>centered data gave a real, non-zero
        correlation (0.895 between the first two components on the demo
        dataset) despite both still being mathematically orthogonal. This
        is why "orthogonal" and "uncorrelated" aren't the same guarantee
        — centering is what closes the gap between them.
    </div>

    <div class="note">
        <strong>How the "uncentered PC1 tracks the mean" finding connects
        to "uncentered PC2 &asymp; centered PC1":</strong> SVD builds
        components sequentially — PC1 is the best rank-1 approximation of
        the data (Eckart&ndash;Young theorem), PC2 is the best rank-1
        approximation of whatever's left after removing PC1, and so on.
        If uncentered PC1 is itself close to the rank-1 "every spectrum
        replaced by the mean spectrum" matrix — which the high correlation
        with the plain mean confirms — then removing it leaves behind
        something close to the mean-centered data. PC2 is then, by
        construction, solving nearly the same problem as centered PC1.
        That's not a coincidence needing two separate explanations; the
        second follows mathematically from the first.
    </div>

    <hr>
    <h2 id="references">References</h2>
    <p style="font-size: 12px;">
    Malinowski, E. R. (2002). <em>Factor Analysis in Chemistry</em>, 3rd ed.
    John Wiley &amp; Sons, New York. (Malinowski IND function, used
    throughout this dialog's Diagnostics tab to help decide how many
    components are real signal versus noise — same reference as SVD
    Analysis's Diagnostics tab, which computes the same metric.)
    <br><br>
    Jackson, J. E. (1991). <em>A User's Guide to Principal Components</em>.
    John Wiley &amp; Sons, New York. (Hotelling T&sup2;, used by the "T&sup2;
    (Hotelling)" colour-by option for spotting outliers — same statistic
    and reference as QC / Outlier Detection.)
    </p>

    </body></html>
    """)

    return help_template.safe_substitute(images)
