# src/help/svd_reconstruction_help.py

"""
Help content for SVD Analysis functionality.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "svd_analysis")

_SCREENSHOT_FILES = {
    "OVERVIEW":             "dialog_overview.png",
    "COMPONENTS_GROUP":     "view_svd_components_group.png",
    "METRIC_DISPLAY":       "metric_display.png",
    "PLOT_DISPLAY":         "plot_display_group.png",
    "PLOT_LAYOUT_ROW":      "plot_layout_row.png",
    "PLOT_LAYOUT_COLUMN":   "plot_layout_column.png",
    "PLOT_SUBSPECTRA_COMBINED":   "plot_subspectra_combined.png",
    "PLOT_COEFFICIENTS_COMBINED": "plot_coefficients_combined.png",
    "PLOT_BOTH_COMBINED":         "plot_both_combined.png",
    "METRICS_TABLE":              "show_all_metrics_table.png",
    "DIAGNOSTICS_TAB":      "diagnostics_tab_overview.png",
    "DIAGNOSTICS_SINGLE":   "diagnostics_single_metric.png",
    "DIAGNOSTICS_COMPARE":  "diagnostics_compare_metrics.png",
    "COMMIT":               "commit_buttons.png",
    "SAVE_DIALOG":          "save_dialog.png",
}

# Cap displayed screenshot width at this many pixels — see data_range_help.py
# for why explicit width/height attributes are used instead of relying on
# CSS to constrain image size.
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


def get_svd_reconstruction_help_title():
    """Return the title for SVD analysis help."""
    return "SVD Analysis — Help"


def get_svd_reconstruction_help_content():
    """
    Get the HTML help content for SVD Analysis.

    Returns:
        str: HTML formatted help content
    """
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders), not str.format()/f-strings — the
    # CSS block below is full of literal { } braces that would collide with
    # .format()-style placeholders.
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
            .ref  { background: #f9f9f9; border: 1px solid #ddd;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; font-style: italic; }
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

    <h1>SVD Analysis</h1>

    <p>SVD (Singular Value Decomposition) decomposes a set of spectra into fundamental
    spectral building blocks called <em>subspectra</em>, ordered by their contribution
    to the total variance. The method is used for noise reduction, baseline correction,
    and spectral reconstruction.</p>

    <div class="screenshot">
        <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="SVD Analysis dialog overview" />
        <p class="caption">The full dialog: the Components tab, with the View SVD Components and Plot display panels on the left and the canvas on the right.</p>
    </div>

    <div class="note">
        <strong>Requirement:</strong> All selected spectra must share an identical x-axis.
        Use the <em>Data Range</em> step to harmonize spectra if needed.
    </div>

    <div class="note">
        <strong>SVD Analysis vs. PCA Scores &amp; Loadings — which one to use:</strong>
        both decompose the same data with the same underlying SVD; they just
        present it for different questions.
        <ul>
            <li><strong>Use this dialog (SVD Analysis)</strong> when your question
                is about one <em>component</em> at a time: "what does component 3
                actually look like, and how strongly does it show up across my
                samples?" A component's shape (subspectrum) and its strength per
                sample (coefficients) are two views of the <em>same</em> object,
                so they're shown paired, side by side. This dialog also adds
                reconstruction tools (rebuild spectra from N components) and
                richer diagnostics (Malinowski IND, residual error) for deciding
                how many components are real signal.</li>
            <li><strong>Use <a href="help://pca_scores">PCA Scores &amp;
                Loadings</a></strong> when your question is about <em>samples</em>
                or <em>variables</em> separately: "do my spectra cluster into
                groups?", "which one is an outlier?", "which wavenumbers drive
                that separation?" There, Scores (sample relationships) and
                Loadings (variable relationships) are shown as separate, full-size
                tabs, since they're usually examined independently — the standard
                convention in chemometrics software (SIMCA, PLS_Toolbox,
                Unscrambler all do the same). It also offers 3D score plots and
                Hotelling's T&sup2; outlier detection.</li>
        </ul>
        In short: SVD Analysis for component-by-component inspection and
        reconstruction; scores/loadings for sample- and variable-level questions.
    </div>

    <hr>
    <h2>Mathematical foundation</h2>

    <p>Given a spectral data matrix <strong>X</strong> of shape
    (n_wavelengths &times; n_spectra), SVD produces:</p>

    <p style="margin-left:20px">
        <span class="fm">X = U &times; diag(s) &times; V<sup>T</sup></span>
    </p>

    <ul>
        <li><strong>U</strong> — matrix of <em>subspectra</em>
            (shape n_wavelengths &times; k), orthonormal spectral basis vectors
            ordered by decreasing variance contribution. These are what you see,
            navigate, and optionally baseline-correct in the dialog.</li>
        <li><strong>s</strong> — vector of <em>singular values</em> (length k),
            always non-negative and decreasing.
            <span class="fm">s_i = &radic;(variance of component i &times; total variance)</span></li>
        <li><strong>V<sup>T</sup></strong> — matrix of <em>coefficients</em>
            (shape k &times; n_spectra). Row i says how much subspectrum i
            contributes to each of the n_spectra original spectra.</li>
    </ul>

    <p>Implementation: <span class="fm">numpy.linalg.svd(X, full_matrices=False)</span>
    (economy/thin SVD — k = min(n_wavelengths, n_spectra)).</p>

    <p><strong>Explained variance</strong> of component i:
    <span class="fm">EV_i = s_i&sup2; / &sum;s_j&sup2; &times; 100%</span></p>

    <div class="note">
        <strong>Mean-centering (SVD settings, "Mean-center spectra before
        SVD"):</strong> unchecked by default here — <strong>X</strong> above
        is decomposed exactly as written, with nothing subtracted first.
        That's the traditional raw-SVD convention this dialog follows, and
        it's why component 1 here usually looks close to a typical raw
        spectrum rather than a deviation from average. Check the box and
        each row of <strong>X</strong> (one wavelength, across every
        selected spectrum) has its own mean subtracted before the
        decomposition — the standard convention for textbook PCA, and the
        default in the related <a href="help://pca_scores">PCA / SVD
        Scores &amp; Loadings</a> dialog instead. Toggling it recomputes
        the whole decomposition instantly (not just how many components
        are kept), since centering changes U, s, and V<sup>T</sup>
        themselves. See that dialog's help for the verified rationale
        (uncentered PC1 mostly tracks the plain per-point mean; centered
        PC1 correlates with uncentered PC2) if you're deciding which
        convention to use for a given analysis.
    </div>

    <hr>
    <h2>Workflow</h2>
    <ol>
        <li>Select and preprocess spectra (data range, baseline, normalization, smoothing).</li>
        <li>Open SVD Analysis — decomposition runs automatically on the selected
            spectra, uncentered by default (tick <strong>Mean-center spectra
            before SVD</strong> in SVD settings to switch conventions — see
            Mathematical foundation above).</li>
        <li>Switch to the <strong>Diagnostics</strong> tab to assess how many components carry
            real signal (singular values plot, residual errors plot, cumulative variance).</li>
        <li>Browse individual subspectra with ◀ / ▶ / Jump to inspect them visually.</li>
        <li>Invert any component whose sign is arbitrary from SVD.</li>
        <li>Tick subspectra in the list to display multiple components simultaneously.</li>
        <li>Use the reconstruction pipeline (separate from this dialog) to rebuild spectra
            from selected components.</li>
        <li>Save results to Excel or text/CSV via the <strong>Save…</strong> button. An
            <em>Include</em> section lets you export just Subspectra, just Coefficients,
            just Metrics, or any combination — all three are included by default. The Excel
            file uses three sheets (<em>Subspectra</em>, <em>Coefficients</em>, <em>Metrics</em>),
            with columns automatically widened so headers are fully visible on first open;
            text/CSV export has the same content (singular values, explained/cumulative
            variance, residual error, and Malinowski IND), either combined into one file or
            split into separate files per category. Subspectrum columns are named simply
            <em>Subspectrum_1</em>, <em>Subspectrum_2</em>, etc. (the variance percentage for
            each is in the Metrics sheet/file instead, rather than crowding the column header).</li>
    </ol>

    <div class="screenshot">
        <img src="$COMMIT" width="$COMMIT_W" height="$COMMIT_H" alt="Help, Save…, and Close buttons" />
        <p class="caption">The dialog's bottom button row: Help on the left, then Save… and Close.</p>
    </div>

    <div class="screenshot">
        <img src="$SAVE_DIALOG" width="$SAVE_DIALOG_W" height="$SAVE_DIALOG_H" alt="Save SVD Analysis Results dialog with File Format, Data Selection, Include, and Output File groups" />
        <p class="caption">The Save… dialog: File Format (Excel or Text/CSV), Data Selection, the Include section (Subspectra / Coefficients / Metrics), and the Output File path with Browse….</p>
    </div>

    <hr>
    <h2>Dialog controls reference</h2>

    <div class="cat">
        <h3>SVD settings</h3>
        <p>Currently just the <strong>Mean-center spectra before SVD</strong>
        checkbox (unchecked by default) — see Mathematical foundation above
        for what it does and why it defaults off here. Sits above View SVD
        Components since it's a decomposition-wide setting, not a
        display/navigation one.</p>
    </div>

    <div class="cat">
        <h3>View SVD Components</h3>

        <div class="screenshot">
            <img src="$COMPONENTS_GROUP" width="$COMPONENTS_GROUP_W" height="$COMPONENTS_GROUP_H" alt="View SVD Components group: Prev, Next, Jump, Invert, Select all, Unselect all, and the component list" />
            <p class="caption">The View SVD Components group: navigation (◀ Prev / Next ▶ / Jump), Invert, Select all / Unselect all, and the component list.</p>
        </div>

        <p><strong>◀ Prev / Next ▶ / Jump:</strong> browse one subspectrum at a time.
        The canvas shows the navigated subspectrum and its V-row coefficients.</p>
        <p><strong>Invert:</strong> multiplies U[:, i] and V[i, :] by &minus;1 simultaneously
        — leaves X unchanged since (&minus;U)(&minus;V<sup>T</sup>) = UV<sup>T</sup>.
        Use whenever a band expected to be positive is pointing downward.</p>
        <p><strong>Select all / Unselect all:</strong> bulk-tick or clear the component list.</p>

        <div class="screenshot">
            <img src="$METRIC_DISPLAY" width="$METRIC_DISPLAY_W" height="$METRIC_DISPLAY_H" alt="Metric display group with metric chooser, number format, and precision controls" />
            <p class="caption">The Metric display group: choice of metric, number format (Fixed or Scientific), and decimal precision.</p>
        </div>

        <p><strong>Metric display</strong> (replaces the old Var.%/&sigma; toggle): choose
        which of the seven metrics (same set as the Diagnostics tab — Singular values,
        Eigenvalue, Explained/Cumulative variance, Residual error, Malinowski IND) appears
        next to each subspectrum in the list and on plot labels, plus the number format
        (Fixed or Scientific) and decimal precision. Some components — especially
        higher-order ones — can have a vanishingly small share that rounds to 0.0% at low
        precision, which looks broken even though the real number is fine.</p>
        <p><strong>Component list:</strong> tick any subset to display them simultaneously
        on the canvas. Component 1 always has the largest contribution.</p>
    </div>

    <div class="cat">
        <h3>Plot display</h3>

        <div class="screenshot">
            <img src="$PLOT_DISPLAY" width="$PLOT_DISPLAY_W" height="$PLOT_DISPLAY_H" alt="Plot display group: Layout Row/Column and Subspectra/Coefficients Separate/Combined options" />
            <p class="caption">The Plot display group: Layout (Row / Column) and the Subspectra / Coefficients Separate-or-Combined options.</p>
        </div>

        <p><strong>Layout Row / Column:</strong> Row = each subspectrum beside its
        coefficient plot. Column = all subspectra in top row, all coefficients below.</p>

        <div class="screenshot">
            <img src="$PLOT_LAYOUT_ROW" width="$PLOT_LAYOUT_ROW_W" height="$PLOT_LAYOUT_ROW_H" alt="Layout: Row, with components 1, 2, and 3 all Separate — each subspectrum paired with its own coefficient plot in the same row" />
            <p class="caption">Layout: Row, Subspectra: Separate, Coefficients: Separate. Each row pairs one component's subspectrum with its own coefficient plot — S1/V1, S2/V2, S3/V3, one row per ticked component.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_LAYOUT_COLUMN" width="$PLOT_LAYOUT_COLUMN_W" height="$PLOT_LAYOUT_COLUMN_H" alt="Layout: Column, with components 1, 2, and 3 all Separate — all subspectra across the top row, all coefficients across the bottom row" />
            <p class="caption">Layout: Column, Subspectra: Separate, Coefficients: Separate. All ticked subspectra (S1, S2, S3) sit across the top row, all coefficient plots (V1, V2, V3) across the bottom row.</p>
        </div>

        <p><strong>Subspectra Separate / Combined:</strong> Separate = one axes per component.
        Combined = all overlaid in one axes — useful for comparing shapes.</p>

        <div class="screenshot">
            <img src="$PLOT_SUBSPECTRA_COMBINED" width="$PLOT_SUBSPECTRA_COMBINED_W" height="$PLOT_SUBSPECTRA_COMBINED_H" alt="Subspectra: Combined — S1, S2, and S3 overlaid in one axes with a legend, coefficients still shown Separate below" />
            <p class="caption">Subspectra: Combined — S1, S2, and S3 overlaid in a single "Combined Subspectra" axes with a legend, so their shapes are easy to compare directly. Coefficients are still shown Separate below.</p>
        </div>

        <p><strong>Coefficients Separate / Combined:</strong> same logic for V-row plots.
        Combined is useful for identifying which spectra are dominated by which component.</p>

        <div class="screenshot">
            <img src="$PLOT_COEFFICIENTS_COMBINED" width="$PLOT_COEFFICIENTS_COMBINED_W" height="$PLOT_COEFFICIENTS_COMBINED_H" alt="Coefficients: Combined — V1, V2, and V3 overlaid in one legended axes below the separate S1/S2/S3 subspectra plots" />
            <p class="caption">Coefficients: Combined — V1, V2, and V3 overlaid in a single "Coefficients" axes with a legend, making it easy to spot which spectra are dominated by which component. Subspectra are still shown Separate above.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_BOTH_COMBINED" width="$PLOT_BOTH_COMBINED_W" height="$PLOT_BOTH_COMBINED_H" alt="Subspectra: Combined and Coefficients: Combined — S1/S2/S3 overlaid on top, V1/V2/V3 overlaid below, each with its own legend" />
            <p class="caption">Subspectra: Combined and Coefficients: Combined together — S1/S2/S3 overlaid in the "Combined Subspectra" axes on top, V1/V2/V3 overlaid in the "Coefficients" axes below, each with its own legend. The most compact view for comparing all ticked components at once.</p>
        </div>

        <p>Right-click the canvas to toggle coefficient visibility or switch plot style
        (scatter vs bar).</p>

        <p><strong>Coefficient X-axis:</strong> a small group above the coefficient plots
        (with its own orange "?" help button) controls what each point on the x-axis
        represents. Three options:</p>
        <ul>
            <li><strong>Spectrum order</strong> — the default: 1, 2, 3, ... in the order
                the spectra were selected.</li>
            <li><strong>Parameter values</strong> — a physical quantity that varies across
                the spectra (temperature, pH, time, concentration, ...), loaded from a text
                file, typed in manually, or dragged and dropped onto the dialog. Values are
                sorted ascending for plotting so the line doesn't zig-zag; they are cleared
                automatically whenever SVD is recomputed.</li>
            <li><strong>Spectrum labels</strong> — each spectrum's name instead of a number,
                shown in the exact order the spectra appear in the main window's list (not
                re-sorted), honoring this dialog's own "Shorten names" checkbox (separate
                from, and off by default regardless of, the main window's setting).</li>
        </ul>
    </div>

    <div class="cat">
        <h3>Diagnostics tab</h3>

        <p>A left control panel and a large canvas, sitting alongside Components as a tab of
        its own (previously a separate window opened via a "Diagnostics…" button). Three view modes:</p>
        <ul>
            <li><strong>Single metric</strong> — plot any one of the seven metrics vs component number.
                An <em>ℹ What does this metric mean?</em> button shows a popup explaining the formula
                and how to interpret the plot.</li>
            <li><strong>Compare two metrics</strong> — scatter plot of any metric on X against any
                metric on Y, with each point labelled by component number. Useful for correlating
                e.g. singular values against residual error.</li>
            <li><strong>Overview (all)</strong> — fixed 2×4 grid showing all seven metrics simultaneously
                (one cell unused).</li>
        </ul>

        <div class="screenshot">
            <img src="$DIAGNOSTICS_SINGLE" width="$DIAGNOSTICS_SINGLE_W" height="$DIAGNOSTICS_SINGLE_H" alt="Diagnostics tab Single metric view with the What does this metric mean button" />
            <p class="caption">"Single metric" view mode, with the "ℹ What does this metric mean?" button.</p>
        </div>

        <div class="screenshot">
            <img src="$DIAGNOSTICS_COMPARE" width="$DIAGNOSTICS_COMPARE_W" height="$DIAGNOSTICS_COMPARE_H" alt="Diagnostics tab Compare two metrics scatter plot labelled by component number" />
            <p class="caption">"Compare two metrics" view mode: a scatter plot of one metric against another, each point labelled by component number.</p>
        </div>

        <div class="screenshot">
            <img src="$DIAGNOSTICS_TAB" width="$DIAGNOSTICS_TAB_W" height="$DIAGNOSTICS_TAB_H" alt="Diagnostics tab in Overview (all) mode showing all seven metrics in a grid" />
            <p class="caption">The Diagnostics tab in "Overview (all)" mode: all seven metrics shown at once in a 2×4 grid (one cell unused).</p>
        </div>

        <p>Seven metrics are available: singular values (σ), eigenvalue (σ²), explained variance per
        component (%), cumulative explained variance (%), cumulative unexplained variance (%), residual
        error E(m), and <strong>Malinowski IND</strong> (see below). Eigenvalue is simply &sigma;&sup2; —
        for raw, unnormalized spectral intensities it commonly reaches 1e8–1e16 or beyond, which is
        expected rather than a sign of a problem; it scales with the square of the data's absolute
        intensity scale, so only its relative size across components is meaningful.</p>
        <p>A <strong>Show all metrics (table)…</strong> button opens every metric, for every
        component, as one table in a larger window — easier to scan precisely than reading
        values off a plot. It has its own Export… button for a quick CSV of just that table.</p>

        <div class="screenshot">
            <img src="$METRICS_TABLE" width="$METRICS_TABLE_W" height="$METRICS_TABLE_H" alt="All SVD Metrics table window listing all seven metrics for every component, with Export and Close buttons" />
            <p class="caption">The "All SVD Metrics" table window: every metric for every component in one sortable table, with its own Export… and Close buttons.</p>
        </div>

        <p>Two <strong>Quick export CSV</strong> buttons at the bottom let you save either all
        metrics to a single file or only the data currently visible in the plot.</p>
    </div>

    <hr>
    <h2>How many components to keep</h2>

    <div class="cat">
        <h3>Singular values plot</h3>
        <p>A steep drop followed by a flat plateau on the log-scale plot marks the
        signal-to-noise boundary. Components in the steep region carry real spectral
        features; those in the flat plateau are dominated by noise.</p>
    </div>

    <div class="cat">
        <h3>Residual error E(m)</h3>
        <p>E(m) = √[ Σᵢ₌ₘ₊₁ σᵢ² / ((n_pts − m − 1)(n_sp − m − 1)) ]</p>
        <p>Root-mean-square residual normalised by degrees of freedom.
        <strong>Monotonically decreasing</strong> for typical spectroscopic data
        where n_pts >> n_sp — there is no meaningful minimum.
        Look for the <em>elbow</em> on the log scale where the rate of decrease
        flattens. Components to the left of the elbow carry real signal; those
        to the right add mostly noise.</p>
    </div>

    <div class="cat">
        <h3>Malinowski IND function</h3>
        <p>IND(m) = RE(m) / (n_sp − m)²</p>
        <p>where RE(m) = √[ Σᵢ₌ₘ₊₁ σᵢ² / (n_pts × (n_sp − m)) ]</p>
        <p>Dividing RE by (n_sp − m)² creates a competing effect: as m increases,
        the numerator (residual) decreases, but the denominator shrinks faster in the
        noise regime, causing IND to <strong>turn upward</strong>.
        The <strong>minimum of IND</strong> is the statistically optimal number of
        components to retain — unlike E(m), IND has a genuine minimum.</p>
        <div class="warn">
            <b>&#9888; IND reliability depends on the n_pts/n_sp ratio:</b><br>
            IND was developed for datasets where n_pts &gt;&gt; n_sp (e.g. 10 spectra
            × 1000 wavelength points). In that regime the denominator (n_sp − m)²
            shrinks fast enough to produce a clear minimum.<br><br>
            When n_pts/n_sp &lt; 10 (nearly square dataset — common with many UV-Vis
            or large spectral series), the denominator shrinks too slowly and the IND
            minimum may point to a much higher N than the true number of components.
            The SVD Diagnostics summary shows a warning when this condition is detected.<br><br>
            <b>For large datasets or continuous series</b> (titrations, concentration
            series, time series), use visual inspection of subspectra and the singular
            value kink as the primary criteria. IND is most reliable for small discrete
            mixture datasets (5–20 spectra).
        </div>
        <div class="tip">
            If the IND minimum disagrees with the singular value kink and the visual
            appearance of subspectra, trust the visual inspection. IND is a guide,
            not a definitive answer.
        </div>
    </div>

    <div class="cat">
        <h3>Cumulative variance</h3>
        <p>The diagnostic window annotates how many components are needed to reach
        95% and 99% of total explained variance. This gives a practical upper bound:
        retaining more than the 99% threshold is rarely justified.</p>
    </div>

    <div class="cat">
        <h3>Visual inspection</h3>
        <p>Subspectra containing real signal look like recognisable spectral features
        (peaks, bands, shoulders). Noise components show random oscillations with no
        structure. A boundary component may show a mix — include it if the features
        are physically meaningful for your measurement.</p>
    </div>

    <hr>
    <h2>Reconstruction modes</h2>

    <p>Reconstruction is performed in the main pipeline (not in this dialog). The SVD
    analysis dialog is for inspection and component evaluation; the pipeline uses the
    results to reconstruct spectra.</p>

    <div class="cat">
        <h3>All components</h3>
        <p><span class="fm">X_rec = U &times; diag(s) &times; V<sup>T</sup></span><br>
        Uses all k components — result is identical to the original data (perfect
        reconstruction, no noise removal). Useful as a sanity check.</p>
    </div>

    <div class="cat">
        <h3>First N components</h3>
        <p><span class="fm">X_rec = U[:,:N] &times; diag(s[:N]) &times; V<sup>T</sup>[:N,:]</span><br>
        Retains only the N highest-variance components. This is the primary
        <strong>noise-reduction mode</strong>. Choose N from the diagnostics plots
        (elbow of residual error curve or singular value kink).</p>
        <div class="tip">
            Start with N = 3&ndash;5 and increase only if additional components
            contain recognisable spectral features. Using too many components
            re-introduces noise.
        </div>
    </div>

    <div class="cat">
        <h3>Only corrected</h3>
        <p>Reconstructs using only those components that have had a baseline correction
        applied. Removes both noise (excluded tail components) and baseline drift
        (corrected within retained components) <strong>in one step</strong>.</p>
        <ul>
            <li>Requires at least one subspectrum with a baseline correction defined.</li>
            <li>Correcting 1&ndash;3 dominant subspectra is usually sufficient for the
                entire dataset.</li>
        </ul>
    </div>

    <hr>
    <h2>Baseline correction via SVD</h2>

    <div class="note">
        <p>A powerful technique: instead of correcting each spectrum individually,
        correct only the dominant subspectra and reconstruct. Because the first
        1&ndash;3 subspectra carry most of the spectral variance, correcting them is
        equivalent to correcting all spectra simultaneously and consistently.</p>
    </div>

    <ol>
        <li>Identify the first few subspectra that show real spectral structure.</li>
        <li>Apply baseline correction to those subspectra using interactive point placement.</li>
        <li>Reconstruct using <em>Only corrected</em> mode.</li>
        <li>Compare with the <em>All</em> mode to validate the correction.</li>
    </ol>

    <div class="tip">
        <strong>Advantage:</strong> Correcting a small number of dominant subspectra is
        often more consistent and efficient than correcting individual spectra, especially
        for large datasets or when spectra have similar but not identical baselines.
    </div>

    <hr>
    <h2>Quick reference table</h2>
    <table>
        <tr><th>Goal</th><th>Tool</th></tr>
        <tr><td>Find how many components carry real signal</td>
            <td>Diagnostics → IND minimum + singular value kink + residual error elbow</td></tr>
        <tr><td>Browse one subspectrum at a time</td>
            <td>◀ / ▶ navigation buttons or Jump spinbox</td></tr>
        <tr><td>Compare two subspectra shapes</td>
            <td>Tick both; Subspectra: Combined</td></tr>
        <tr><td>Which spectra are dominated by component i?</td>
            <td>Tick component i; inspect coefficient plot (V row)</td></tr>
        <tr><td>Denoise all spectra</td>
            <td>Reconstruct with First N components</td></tr>
        <tr><td>Remove baseline and noise simultaneously</td>
            <td>Correct dominant subspectra → reconstruct with Only corrected</td></tr>
        <tr><td>Export singular values / residual errors quickly</td>
            <td>Diagnostics tab → CSV export buttons</td></tr>
    </table>

    <hr>
    <h2>References</h2>

    <div class="ref">
        <strong>Palacky, J., et al. (2011).</strong>
        "SVD-based method for intensity normalization, background correction and
        solvent subtraction in Raman spectroscopy exploiting the properties of
        water stretching vibrations."
        <em>Journal of Raman Spectroscopy</em> <strong>42</strong>(7): 1528&ndash;1539.
    </div>

    <div class="ref">
        <strong>Malinowski, E. R. (2002).</strong>
        <em>Factor Analysis in Chemistry</em>, 3rd ed.
        John Wiley &amp; Sons, New York.
    </div>

    </body>
    </html>
    """)

    return help_template.safe_substitute(images)
