# src/help/mcr_als_help.py

import os
import struct
from pathlib import Path
from string import Template

from src.modules.utils.resource_path import resource_path


# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build. Same mechanism as
# band_ratio_help.py — see that file for the full rationale.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "MCR-ALS")

_SCREENSHOT_FILES = {
    "OVERVIEW":         "dialog_overview.png",
    "SETTINGS":         "settings_panel.png",
    "PURE_SPECTRA_TAB": "pure_spectra_tab.png",
    "CONCENTRATIONS_TAB": "concentrations_tab.png",
    "RECONSTRUCTION_TAB": "reconstruction_tab.png",
    "REFERENCE_PANEL":  "reference_spectra_panel.png",
    "FIT_QUALITY_TAB":  "fit_quality_tab.png",
    "EXPORT_DIALOG":    "export_components_dialog.png",
    "SAVE_DIALOG":      "save_dialog.png",
}

# Cap displayed screenshot width at this many pixels — see
# band_ratio_help.py's _MAX_IMG_WIDTH for the full explanation (Qt's
# rich-text engine doesn't reliably honor CSS max-width on <img>).
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
            # (e.g. these dialogs' screenshots haven't been captured yet)
            # — fall back to a fixed box instead of crashing the whole
            # help page.
            display_w, display_h = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)

        values[f"{key}_W"] = str(display_w)
        values[f"{key}_H"] = str(display_h)

    return values


def _fill_dataset_paths(html):
    """Substitute the real, absolute location of the synthetic test datasets
    into the help page.

    The link used to be a hand-written relative href ("file:///./resources/…"),
    which cannot work: help pages are written out to a per-user app-data folder
    and opened from THERE (see help_window.py), so a path relative to the page
    points into that folder, not into the application folder. Resolving the
    real absolute path here — the same way main_controller does, honouring
    PyInstaller's _MEIPASS when frozen — makes the link actually open.
    """
    import os, sys
    base = getattr(sys, '_MEIPASS', None)
    if base is None:
        # src/help/<this file> -> up two levels to the application root
        base = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    folder = os.path.join(base, 'resources', 'test_data', 'synthetic')
    # pathname2url gives a correctly-formed file URL on both Windows
    # ('C:\\app\\resources' -> '/C:/app/resources') and POSIX, without the
    # double-slash a naive 'file:///' + path produces on Linux/macOS.
    from urllib.request import pathname2url
    url = 'file://' + pathname2url(folder)
    return (html.replace('__DATASETS_URL__', url)
                .replace('__DATASETS_DIR__', folder))


def get_mcr_als_help_title():
    return 'MCR-ALS (Multivariate Curve Resolution) — Help'

def get_mcr_als_help_content():
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which
    # would collide with .format()-style placeholders. Dataset-path tokens
    # (__DATASETS_URL__ etc.) are handled separately by _fill_dataset_paths,
    # after this substitution, since they use a different, non-$ token style.
    html = Template("""
    <html><head><style>
        body  { font-family:Arial,sans-serif; margin:20px; line-height:1.6; font-size:13px; }
        h1    { color:#2E7D32; border-bottom:2px solid #2E7D32; }
        h2    { color:#1565C0; margin-top:22px; }
        .tip  { background:#E8F5E9; border-left:4px solid #2E7D32; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .note { background:#E3F2FD; border-left:4px solid #1565C0; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .warn { background:#FFF8E1; border-left:4px solid #F9A825; padding:10px 14px; border-radius:3px; margin:8px 0; }
        table { border-collapse:collapse; width:100%; margin:8px 0; }
        th    { background:#E3F2FD; text-align:left; padding:6px 8px; }
        td    { border-bottom:1px solid #e0e0e0; padding:5px 8px; vertical-align:top; }
        ul,ol { padding-left:20px; } li { margin:3px 0; }
        hr    { border:none; border-top:1px solid #ddd; margin:20px 0; }
        .fm   { font-family:monospace; background:#ececec; padding:1px 5px; border-radius:3px; }
        .screenshot { margin:12px 0; text-align:center; }
        .screenshot img { border:1px solid #dee2e6; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,0.15); }
        .screenshot .caption { font-size:0.9em; color:#7f8c8d; font-style:italic; margin-top:6px; }
    </style></head><body>

    <h1>MCR-ALS (Multivariate Curve Resolution — Alternating Least Squares)</h1>

    <div class="screenshot">
        <img src="$OVERVIEW" width="${OVERVIEW_W}" height="${OVERVIEW_H}" alt="MCR-ALS dialog: settings panel on the left, Pure Spectra/Concentrations/Reconstruction/Fit Quality tabs on the right" />
        <p class="caption">The full MCR-ALS dialog: settings on the left, results tabs on the right.</p>
    </div>

    <p>MCR-ALS decomposes the spectral data matrix
    <strong>D</strong> (n&nbsp;spectra &times; n&nbsp;wavelengths) into two
    matrices, found by alternating constrained least-squares fits:</p>
    <ul>
        <li><strong>ST</strong> (n&nbsp;components &times; n&nbsp;wavelengths)
            &mdash; pure component spectra, one per row.</li>
        <li><strong>C</strong> (n&nbsp;spectra &times; n&nbsp;components)
            &mdash; concentration profiles. C[i, k] is how much component k
            contributes to spectrum i.</li>
    </ul>
    <p>D &asymp; C &times; ST, found iteratively: given ST, solve for C;
    given the new C, solve for ST; repeat until the fit stops improving.</p>

    <div class="note">
        <strong>MCR-ALS vs NMF:</strong> both decompose spectra into
        non-negative components and abundances, and often give very similar
        results. The difference is how non-negativity is enforced: NMF uses
        a specific multiplicative-update algorithm where non-negativity of
        both factors is structural (built into the algorithm itself).
        MCR-ALS instead applies non-negativity as an explicit constraint
        (via NNLS) at each step of an otherwise ordinary least-squares fit —
        which is why it's straightforward here to turn either constraint
        off independently (e.g. non-negative concentrations but
        unconstrained spectra), something NMF can't do.
    </div>

    <hr>
    <h2>Read this first: what this tool can and can't tell you</h2>
    <div class="warn" style="border-left-color:#c0392b; background:#FDEDEC;">
        <strong style="color:#c0392b;">Baseline-correct first &mdash; this
        isn't optional.</strong> If your spectra haven't been baseline
        corrected (even roughly &mdash; the background needs to be
        <em>reduced</em>, not perfectly removed), MCR-ALS won't just give a
        slightly worse answer: with real Raman/IR data, an uncorrected
        fluorescence background routinely accounts for &gt;99.9% of the
        data's total variance, leaving essentially nothing for the
        components to tell real chemistry apart with. Different runs then
        disagree wildly with each other &mdash; a "Consensus among N
        near-best runs" in the single digits (or noisy, spiky-looking
        components) is the signature of this, not a subtle ambiguity to
        interpret. <strong>Run Baseline correction (even an imperfect one)
        before MCR-ALS.</strong> Recommended pipeline: Data range
        &rarr; Baseline correction &rarr; Normalisation &rarr; MCR-ALS.
    </div>

    <div class="warn">
        <strong>A good-looking fit does not mean you found the real pure
        spectra.</strong> This isn't a caveat to skim past — it's the single
        most important thing to know before trusting any result here.
        MCR-ALS (and NMF) can find several genuinely different sets of
        "pure" components that all reconstruct your data equally well.
        Nothing in the math tells the software which one is chemically
        real; only outside information can (a real reference spectrum of
        one pure substance, chemical knowledge of which bands a substance
        should or shouldn't have, or a sample you know is genuinely pure).
        Confirmed directly and repeatedly with test data in this app's
        development: the same dataset can give a "perfect," self-consistent
        fit with completely wrong components, using completely ordinary
        settings — this is a property of the method, not a bug to expect
        a future fix for.
    </div>
    <ul>
        <li><strong>A low lack-of-fit number is not evidence of a correct
            answer</strong> — only that the model reproduces the data. Many
            different, wrong answers can fit just as well as the right one.</li>
        <li><strong>"X/N runs within 10% of best" is a weaker check than it
            sounds.</strong> It only means the attempts agreed on fit
            *quality* — they can all agree on quality while all being the
            same wrong answer. It does not mean the components found are
            correct.</li>
        <li><strong>"Consensus among N near-best runs" is a stronger check</strong>
            (it compares actual component shapes, not just fit scores), but
            still isn't proof — it only tells you the runs you happened to
            try agree with each other, not that a different, equally valid
            answer doesn't exist elsewhere.</li>
        <li><strong>Turn Closure on only if you have a real, specific
            reason to believe your total concentration is genuinely
            constant.</strong> It's a real constraint on the fit, not a
            cosmetic option — turning it on for data that doesn't actually
            satisfy it can make the correct answer mathematically
            impossible to find, not just harder to find. (Off by default
            for this reason.)</li>
        <li><strong>For data that requires non-negativity to be turned off</strong>
            (e.g. CD spectra, which are genuinely signed) — expect
            dramatically less reliable results. Non-negativity turns out to
            be the single most powerful thing ruling out wrong answers;
            without it, this kind of blind decomposition is often not the
            right tool at all. Real CD analysis typically uses known
            reference spectra instead, for this reason.</li>
        <li><strong>More/sharper spectral bands generally help</strong>
            (Raman-type data with many narrow peaks tends to give more
            reliable results than broad, heavily-overlapping absorption
            bands) — but this helps the odds, it doesn't guarantee a
            unique answer.</li>
    </ul>

    <hr>

    <hr>
    <h2>MCR-ALS and NMF: how they correspond, and which to use</h2>
    <p>These two tools do the same job — take a set of mixed spectra and
    split them into a few underlying building blocks plus how much of each is
    present in every spectrum — and from your point of view they behave
    almost identically (same tabs, same "Run N times, keep best", same
    Elbow/Fit-Quality diagnostics, same rotational-ambiguity caveats). They
    use different maths and different words for the same two outputs:</p>
    <table>
        <tr><th></th><th>MCR-ALS</th><th>NMF</th></tr>
        <tr><td>The building-block spectra</td>
            <td><strong>Pure component spectra</strong> (ST), shown in the
                <em>Pure Spectra</em> tab</td>
            <td><strong>Spectral components</strong> (H), shown in the
                <em>Components</em> tab</td></tr>
        <tr><td>How much of each per spectrum</td>
            <td><strong>Concentrations</strong> (C)</td>
            <td><strong>Scores</strong> / weights (W), shown in the
                <em>Concentrations</em> tab</td></tr>
        <tr><td>Non-negativity</td>
            <td>Optional (checkboxes) — can be turned off for signed data</td>
            <td>Always on (built into the method)</td></tr>
        <tr><td>Handles negative data (CD, uncorrected baseline)</td>
            <td>Yes, if you uncheck non-negativity</td>
            <td>No — negatives are clipped/offset away, which distorts
                the fit</td></tr>
    </table>
    <p><strong>Speed and determinism.</strong> NMF is generally the faster of
    the two (multiplicative updates), and with <span class="fm">nndsvda</span>
    /<span class="fm">nndsvd</span> it is fully deterministic — the same input
    gives the same answer every run, so it's an excellent quick, reproducible
    first look. MCR-ALS solves a constrained least-squares problem at every
    iteration, which costs more time; what you buy with that time is the
    ability to <em>impose knowledge</em> — closure, non-negativity on one
    factor only, signed spectra. Both tools now support reference anchoring.</p>

    <p><strong>Advantages / disadvantages at a glance:</strong></p>
    <ul>
        <li><strong>NMF advantages:</strong> faster; deterministic; fewer knobs
            to get wrong; very good on clean, baseline-corrected, non-negative
            data.<br>
            <strong>NMF disadvantages:</strong> cannot handle negative data at
            all (it clips negatives to zero); cannot impose closure; no way to
            relax non-negativity on just one factor.</li>
        <li><strong>MCR-ALS advantages:</strong> constraints are its whole point
            — closure, per-factor non-negativity, reference anchoring; handles
            signed data (CD) when you switch ST non-negativity off; the
            constraints often make components far more physically
            interpretable.<br>
            <strong>MCR-ALS disadvantages:</strong> slower; more settings to
            understand; a wrongly-applied constraint (especially closure) can
            actively prevent it finding the right answer.</li>
    </ul>

    <p><strong>Both share the same fundamental limitation:</strong> rotational
    ambiguity. A low lack-of-fit never proves the components are chemically
    correct — many different-looking decompositions can fit equally well. Use
    "Run N times, keep best" and check the consensus figure, and anchor known
    components with the Reference spectra panel wherever you can.</p>

    <p><strong>Which one should I use?</strong></p>
    <ul>
        <li><strong>Non-negative data (ordinary absorption, Raman, IR
            intensities), baseline-corrected:</strong> both work and usually
            agree. NMF is the faster, fully deterministic default and is
            excellent for a quick, reproducible first look. MCR-ALS is worth
            preferring when you want to <em>impose meaningful constraints</em>
            — closure (concentrations sum to 100%), or non-negativity on only
            one factor — or when you have known pure spectra to build on;
            these constraints often give more physically interpretable
            components. Running both and comparing is a good sanity check:
            broad agreement is reassuring, disagreement flags that the
            decomposition isn't uniquely pinned down.</li>
        <li><strong>Signed data (circular dichroism, or data you haven't
            baseline-corrected):</strong> use MCR-ALS with non-negativity
            <em>unchecked</em>. NMF is not suitable — it can't represent real
            negative peaks. Be aware that with non-negativity off, the main
            constraint pinning the result down is gone, so the solution is
            especially ambiguous (see "what this tool can and can't tell
            you"); for CD specifically, dedicated reference-based methods are
            usually the right tool rather than blind resolution.</li>
        <li><strong>Either way:</strong> don't read exact numbers off a single
            blind run. Use "Run N times, keep best" and check the consensus
            figure, and lean on the normalised-to-100% view for interpretable
            relative amounts.</li>
    </ul>

    <div class="note">
        <strong>All spectra must share an identical x-axis.</strong> If they don't,
        MCR-ALS/NMF will refuse to run and tell you which spectrum differs — exactly
        as SVD and PCA already do. Use the <strong>Data Range</strong> operation to
        put the spectra on a common axis first.
        <br><br>
        This is deliberate. These tools used to silently resample every spectrum onto
        the first one's grid, which hid two real problems: a different step size was
        quietly re-gridded, and a spectrum covering a <em>narrower</em> range was
        flat-extrapolated across the gap — invented numbers, then fitted as if they
        were measurements. Harmonising the axes is a separate, visible step that
        belongs in Data Range, where you can see and check what it did.
        <br><br>
        (The <em>order</em> of the x-values doesn't matter — descending axes, as Raman
        files often use, are fine. It is a <em>mismatch</em> between spectra that is
        rejected, not the direction.)
    </div>
    <hr>
    <h2>Settings</h2>
    <table>
        <tr><th>Setting</th><th>Description</th></tr>
        <tr><td><strong>Components</strong></td>
            <td>Number of components to resolve. Start with a small number
                (2&ndash;4) and increase until the lack-of-fit stops
                improving significantly (see the Fit Quality tab’s Elbow view).</td></tr>
        <tr><td><strong>Initialisation</strong></td>
            <td>The plain <strong>Run MCR-ALS</strong> button always uses a
                deterministic <span class="fm">svd</span> starting guess
                (from the leading right-singular vectors of the data), so it
                gives the same result every run. There is no initialisation
                dropdown: a single <em>random</em> start is unreliable on its
                own, so random restarts are reached only through
                <strong>Run N times, keep best</strong> below.</td></tr>
        <tr><td><strong>Run N times, keep best</strong></td>
            <td>Always available. Runs several fits from different random
                seeds and keeps whichever is most representative of the
                near-best group (lowest lack-of-fit, then most structurally
                consistent with the other near-best runs), instead of
                clicking Run MCR-ALS repeatedly by hand. The status line then
                reports how many runs landed within 10% of the best and how
                strongly the near-best runs agree — a stronger reliability
                check than any single run.</td></tr>
        <tr><td><strong>Max iterations</strong></td>
            <td>Maximum ALS iterations. The fit stops early once the
                lack-of-fit changes by less than a small tolerance between
                consecutive iterations (shown as "converged" in the status
                line) — increase this if it reports not converging.</td></tr>
        <tr><td><strong>Non-negative concentrations (C)</strong></td>
            <td>Enforces C &ge; 0 via NNLS at every iteration — the
                standard choice, since a negative concentration is usually
                not physically meaningful. Turn off if you have a specific
                reason to allow it (rare).</td></tr>
        <tr><td><strong>Non-negative spectra (ST)</strong></td>
            <td>Enforces ST &ge; 0 via NNLS at every iteration. Turn off if
                a genuinely negative-valued component is expected (e.g. CD
                spectra, or difference/derivative spectra as one of the
                pure components).</td></tr>
        <tr><td><strong>Normalize spectra each iteration</strong></td>
            <td>Rescales each component's ST row to unit norm every
                iteration, pushing the compensating scale factor into C.
                C &times; ST is mathematically unaffected by C *= k,
                ST /= k for any k — without pinning this down, the two
                factors can drift to arbitrarily large or small scales over
                many iterations. Leave this on unless you have a specific
                reason to compare raw, unnormalized scales.</td></tr>
        <tr><td><strong>Offset components for clarity</strong></td>
            <td>Shifts each component vertically on the Pure Spectra tab so
                overlapping curves are readable. Turn off to compare
                component shapes/intensities directly on the same
                baseline.</td></tr>
    </table>

    <div class="screenshot">
        <img src="$SETTINGS" width="${SETTINGS_W}" height="${SETTINGS_H}" alt="MCR-ALS settings panel: Components, Run N times keep best, Max iterations, and the non-negativity/normalize checkboxes" />
        <p class="caption">The settings panel: components count, constraints, and Run N times, keep best.</p>
    </div>

    <hr>
    <h2>Pure Spectra tab</h2>
    <p>The resolved pure-component spectra (rows of ST), offset vertically
    for clarity. The percentage shown is each component's share of the
    <em>modeled signal</em> — its contribution (concentration &times;
    spectral shape together, not the spectral shape alone), as a fraction
    of the total contribution summed across all components. This always
    adds up to exactly 100% by construction. It's a deliberately different
    (and more robust) convention than literally "% of the data's total
    variance": that version was tried and reverted, since it could compare
    each component's contribution against a differently-scaled reference
    and occasionally report a single component "explaining" over 100% on
    its own, or every component reporting a tiny fraction of a percent
    despite a good fit. What's shown now always means the same thing:
    "of the variation this model captures, how much does each component
    account for."</p>

    <div class="screenshot">
        <img src="$PURE_SPECTRA_TAB" width="${PURE_SPECTRA_TAB_W}" height="${PURE_SPECTRA_TAB_H}" alt="Pure Spectra tab: resolved pure-component spectra offset vertically, with each component's percentage share of the modeled signal" />
        <p class="caption">The Pure Spectra tab: each resolved pure-component spectrum (rows of ST).</p>
    </div>

    <hr>
    <h2>Concentrations tab</h2>
    <p>Shows each component's concentration/abundance in every spectrum
    (columns of C). Components are always ordered by explained variance —
    "Component 1" is the largest, "Component 2" the next, and so on.
    Spectra dominated by a single component stand out with high values for
    that component.</p>
    <ul>
        <li><strong>Plot type:</strong> <span class="fm">Grouped bars</span>
            (default) — one bar per component per spectrum, side by side.
            <span class="fm">Stacked bars</span> — each spectrum's bars
            stacked into one, total height = sum of all components.
            <span class="fm">Lines</span> — one line per component across
            spectrum index; far more readable than either bar style once
            you have more than ~30&ndash;40 spectra, where individual bars
            become too thin to distinguish.</li>
        <li><strong>Normalize to 100% per spectrum:</strong> the raw
            concentration scale is arbitrary — C &times; ST is mathematically
            unchanged by multiplying a component's concentration by k and
            dividing its spectrum by the same k, so the absolute numbers on
            the y-axis have no inherent meaning on their own. Checking this
            rescales each spectrum's row of C to sum to 100%, showing
            relative composition instead (e.g. "80% component 1, 15%
            component 2, 5% component 3"), which is usually far easier to
            interpret. Display only — doesn't change the underlying fit or
            what gets saved/exported.</li>
        <li><strong>Label rotation / font size / truncation:</strong> same
            controls as Cluster Analysis's dendrogram options — rotate
            labels (90&deg;/45&deg;/0&deg;), fix the font size or let it
            auto-shrink as spectrum count grows, and choose whether long
            labels show in full, truncated to the first N characters, or
            truncated to the last N characters (useful when the
            distinguishing part of a label is at the end, e.g.
            "...back-ii").</li>
        <li><strong>Use spectrum index (1, 2, 3, ...) instead of labels:</strong>
            replaces the spectrum labels on the axis/table with plain
            position numbers — handy when labels are long, or not
            meaningful for this view. Truncation has no effect while this
            is checked, since there's nothing left to truncate.</li>
    </ul>

    <div class="screenshot">
        <img src="$CONCENTRATIONS_TAB" width="${CONCENTRATIONS_TAB_W}" height="${CONCENTRATIONS_TAB_H}" alt="Concentrations tab: grouped bars, stacked bars, or lines showing each component's concentration per spectrum" />
        <p class="caption">The Concentrations tab: each component's concentration in every spectrum (columns of C).</p>
    </div>

    <hr>
    <h2>Reconstruction tab</h2>
    <p>Use the <strong>Reconstruction preview</strong> list on the left to
    pick which spectrum to inspect. Compares that spectrum (black,
    <strong>Original</strong>) with what the model predicts for it (red
    dashed, <strong>Reconstructed</strong> = C[i] &times; ST). Coloured
    fills show each component's individual contribution.</p>
    <p><strong>Residual</strong> (<em>Original &minus; Reconstructed</em>)
    is shown two ways: as a grey hatched region in the main panel — hatched
    rather than solid so it's never confused with one of the component
    colour fills — and as an actual plotted curve in the smaller panel
    directly below, at its own y-scale. The hatch shows roughly where it
    sits relative to the data; the curve below shows what it actually looks
    like, since residuals are usually far too small to read clearly plotted
    at the same scale as the original data. A good fit means this residual
    curve is small and roughly flat across the whole spectrum.</p>

    <div class="screenshot">
        <img src="$RECONSTRUCTION_TAB" width="${RECONSTRUCTION_TAB_W}" height="${RECONSTRUCTION_TAB_H}" alt="Reconstruction tab: original vs reconstructed spectrum, coloured component fills, and the residual panel below" />
        <p class="caption">The Reconstruction tab: Original vs Reconstructed, with per-component fills and the Residual panel below.</p>
    </div>

    <hr>
    <h2>Fit Quality tab (Per spectrum, Elbow, and Median residual)</h2>
    <p>This one tab holds three views, chosen from the <strong>Show:</strong>
    dropdown on the left. The first judges the quality of the run you just
    computed; the other two help you choose how many components to use by
    re-running at several component counts. "Max components to test" (also on
    the left) controls how far the two "vs component count" views sweep, and
    is greyed out for the per-spectrum view, which doesn't use it.</p>

    <p><strong>Show: Per spectrum (current run)</strong> — the Reconstruction
    tab only shows one spectrum at a time; this shows all of them at once, as
    a bar chart of each spectrum's relative residual (100 &times; the size of
    its residual, as a percentage of the spectrum's own total signal). Bars
    noticeably above the dashed median line are highlighted in red — a quick
    way to spot a spectrum that fits much worse than the rest. This is a
    visual aid, not a formal statistical test: use it to decide which spectra
    are worth a closer look in the Reconstruction tab, not as a pass/fail
    cutoff.</p>

    <p><strong>Show: Elbow — lack of fit vs component count</strong> — runs
    MCR-ALS for each number of components from 2 up to "Max components to
    test" and plots the aggregate lack-of-fit (%). Look for the "elbow": the
    point where adding more components stops reducing lack-of-fit
    meaningfully — that's usually a sensible number of components. The result
    is cached, so switching views and back without changing settings reuses
    it instead of recomputing.</p>
    <div class="note">
        Unlike the main Run, every component count here runs the full
        iteration budget with early stopping disabled — comparing counts
        fairly requires each to be pushed to the same depth, since letting
        each stop as soon as it "looks" converged can leave some counts cut
        off earlier than others purely by chance, which can otherwise show up
        as a higher component count looking spuriously worse than a lower one.
    </div>

    <div class="note">
        <strong>If the elbow (or median) curve looks like a random zig-zag,
        check the y-axis scale first.</strong> On clean, low-noise data the fit
        can already be <em>exact</em> at the correct component count — every
        value on the curve is then zero to numerical precision (1e-9 % or
        smaller). Auto-scaling turns that floating-point dust into a dramatic
        zig-zag that looks like real structure, and it is tempting to read an
        "elbow" into pure noise. Both plots now detect this: when every value
        is below 0.05 % they pin the y-axis and say so directly on the plot.
        The correct reading in that case is "the smallest component count shown
        already reproduces the data" — not "7 components is worse than 6".
    </div>

    <p><strong>Show: Median residual vs component count</strong> — the same
    sweep, but tracks the <em>median</em> of the per-spectrum relative
    residuals instead of the aggregate lack-of-fit. These are genuinely
    different statistics and can legitimately disagree:</p>
    <ul>
        <li>Lack-of-fit (the Elbow view) is an aggregate over the whole
            dataset, computed from the total sum of squared residuals — a few
            spectra with unusually large absolute residuals can dominate it,
            making it look like adding components helps a lot even if most
            spectra were already fine.</li>
        <li>Median relative residual (this view) reflects how the
            <em>typical</em> spectrum fits, and is far less sensitive to a
            handful of problem spectra.</li>
    </ul>
    <p>If the two disagree — e.g. the Elbow view shows a sharp drop at some
    component count but the median barely moves — it usually means a
    <em>subset</em> of your spectra are driving that improvement, while most
    spectra were already reasonably well fit with fewer components. Worth
    checking which spectra those are (switch to "Per spectrum" and look for
    the red bars) — if it's the same few spectra at every component count,
    they may have some other issue (noise, a genuinely different state, an
    artifact) that adding components won't really fix.</p>

    <div class="screenshot">
        <img src="$FIT_QUALITY_TAB" width="${FIT_QUALITY_TAB_W}" height="${FIT_QUALITY_TAB_H}" alt="Fit Quality tab: per-spectrum residual bars, Elbow lack-of-fit vs component count, or Median residual vs component count" />
        <p class="caption">The Fit Quality tab: Per spectrum, Elbow, and Median residual views.</p>
    </div>

    <hr>
    <h2>Reference spectra (anchoring to known components)</h2>
    <p>This optional panel (tick its title to enable it) is the single most
    effective way to escape MCR's rotational ambiguity: if you already know
    what one or more of your pure components look like — a measured pure
    standard — you can <em>anchor</em> a component slot to that known
    spectrum instead of letting the fit guess it.</p>
    <ul>
        <li><strong>How to use it.</strong> Load your known pure spectrum
            into the app and include it in the selection you send to MCR-ALS.
            Then, in this panel, pick it from the dropdown next to the
            component slot you want it to occupy. You can anchor as many
            slots as you have references for; leave the rest on "(none)" for
            the fit to resolve freely.</li>
        <li><strong>Hold references fixed</strong> (default): the anchored
            component is held exactly equal to your known spectrum for the
            whole fit — the strongest anchoring, and what pins the remaining
            components down. Unticked, the reference is used only as the
            starting guess and is then free to drift — gentler, for when your
            reference is close but not identical to the true component.</li>
        <li><strong>References are external</strong> (default): your reference
            is a previously-measured standard, not one of the mixtures in your
            experimental series, so it is used only as a known component shape
            and is <em>removed</em> from the set of spectra being decomposed.
            Untick only if the reference genuinely is one of the samples in
            your series (e.g. the first spectrum of a melting curve really is
            the pure duplex) and you want it fitted too. This matters: leaving
            a near-pure spectrum in the fitted data changes what is being
            decomposed.</li>
        <li><strong>Component order is preserved</strong> when references are
            used: the slot you assign a reference to stays that component
            (the usual "reorder by importance" is switched off, so
            "Component 2 = my known spectrum" stays true).</li>
    </ul>
    <div class="note">
        <strong>Practical example.</strong> You often <em>do</em> know one
        endpoint of an experiment: the Raman spectrum of the fully disordered
        state (e.g. DNA held at high temperature, or a fully denatured
        protein), or a pure reagent measured on its own. Anchoring that known
        endpoint is exactly the situation this panel is for, and it typically
        cleans up the component mixing you would otherwise see.
    </div>
    <p><strong>Why it helps so much.</strong> On a hard, ambiguous test set
    (signed CD data, where a free fit recovered the true components only
    ~0.79 on a 0&ndash;1 similarity scale), anchoring the known components
    lifted recovery to ~0.98 — and on noisy Raman it took ~0.85 to ~0.999.
    Fixing what you know leaves far less room for the rest of the fit to
    drift. For non-negative data a single deterministic run with references
    is usually enough; for signed (CD) data, combine references with
    <strong>Run N times, keep best</strong>, since the free components still
    need random restarts to find their best orientation.</p>
    <div class="note">
        A reference is matched onto your data's x-axis automatically and its
        overall scale is absorbed into the concentrations, so only its
        <em>shape</em> is imposed — you don't need it on the same intensity
        scale as your mixtures, just the same kind of measurement over an
        overlapping x-range.
    </div>

    <div class="screenshot">
        <img src="$REFERENCE_PANEL" width="${REFERENCE_PANEL_W}" height="${REFERENCE_PANEL_H}" alt="Reference spectra panel: component-slot dropdowns, Hold references fixed, and References are external checkboxes" />
        <p class="caption">The Reference spectra panel: anchor a component slot to a known pure spectrum.</p>
    </div>
            then normalisation before MCR-ALS, for the same reason as NMF —
            an uncorrected fluorescence background will dominate the first
            component. Recommended pipeline: Data range \u2192 Baseline
            correction \u2192 Normalisation \u2192 MCR-ALS.</li>
        <li><strong>Start with 2&ndash;4 components</strong> and use the
            Fit Quality tab’s Elbow view and lack-of-fit to justify adding more.</li>
        <li><strong>Compare against NMF and PCA</strong> for the same
            selection — MCR-ALS, NMF, and PCA loadings should capture
            similar underlying spectral features from different
            mathematical angles; substantial disagreement between them is
            worth investigating.</li>
        <li><strong>Mismatched x-ranges produce spurious components</strong>
            — same caveat as NMF: values outside a spectrum's own range get
            held flat (not extrapolated) when aligning to a common grid,
            which can create an artificial discontinuity that MCR-ALS
            mistakes for a real component. A warning appears below the Run
            button if this is detected.</li>
        <li><strong>Rotational ambiguity.</strong> Like NMF, MCR-ALS
            solutions are not unique — different starting points can
            converge to different (but equally valid, similarly low
            lack-of-fit) decompositions, especially with more components or
            more collinear spectra. If results look unexpected, run
            "Run N times, keep best" and check the consensus figure it
            reports.</li>
        <li><strong>Flat, exactly-zero stretches in a component.</strong>
            Non-negative least squares (the constraint behind "Non-negative
            spectra") tends to produce genuinely sparse solutions — exact
            zeros, not just small values — over whole stretches of a
            spectrum whenever two or more components could explain that
            region almost equally well. This is a real, documented property
            of NNLS-constrained methods when components overlap or their
            concentration profiles are correlated, not a bug, and it can
            happen to any component, not only a weak one. Check the
            Reconstruction tab: if the summed model still matches your real
            data in that region, the overall fit is fine — it's specifically
            the split between components that's ambiguous there. Unchecking
            "Non-negative spectra (ST)" or reducing the number of components
            can reduce how often this happens.</li>
    </ul>



    <div class="note">
        <strong>Can concentrations really be negative?</strong> Physically, no —
        you cannot have a negative amount of a substance, which is why
        "Non-negative concentrations (C)" is on by default and should normally
        stay on. The option to switch it off exists because the underlying
        least-squares maths is perfectly happy to produce negative values (a
        negative amount of one component "cancelling" an overshoot in another);
        the constraint is what forbids that chemical nonsense.
        <br><br>
        Turn it off only when the concentration axis is <em>not</em> a physical
        amount — i.e. when you are deliberately using MCR-ALS as a general
        bilinear decomposition and treating C as abstract coefficients (say, a
        difference-spectrum series where a "concentration" legitimately means
        "how much of this pattern to add or subtract"). Outside such cases,
        negative concentrations are a red flag, not a result, and the main
        honest use of the switch is diagnostic: if turning non-negativity off
        markedly improves the fit, something else is wrong — most often an
        uncorrected baseline, or too few components.
    </div>
    <hr>
    <h2>When does Closure apply? (concrete experiments)</h2>
    <p><strong>Closure</strong> (an MCR-ALS setting) forces every spectrum's
    concentrations to sum to 100% <em>during</em> the fit. It is only correct
    when your system is genuinely <em>closed</em>: total material is conserved
    and species only convert into one another. Getting this wrong is costly —
    switch closure on for a system that is not closed and the true answer can
    become mathematically unreachable, not merely harder to find.</p>

    <p><strong>Closure DOES apply (turn it ON):</strong></p>
    <ul>
        <li><strong>DNA/RNA melting.</strong> A duplex melts into single strands
            as temperature rises. Total nucleic acid is conserved, so duplex% +
            single-strand% = 100% in every spectrum. (Same for a three-state
            melt: duplex &rarr; intermediate &rarr; single strand.)</li>
        <li><strong>Protein folding/unfolding.</strong> Folded &rarr; unfolded
            (&plusmn; intermediates) at constant total protein — the fractions of
            each conformational state sum to 1.</li>
        <li><strong>Conformational or tautomeric equilibria.</strong> A &harr; B
            (helix &harr; coil, keto &harr; enol) at fixed total concentration:
            you're watching a fixed total redistribute between forms.</li>
        <li><strong>An acid&ndash;base / pH titration of a fixed amount of
            analyte</strong>, where protonated and deprotonated forms
            interconvert and total analyte stays constant.</li>
        <li><strong>A closed reaction A &rarr; B (&rarr; C)</strong> with nothing
            entering or leaving and no side products outside your component
            set.</li>
    </ul>

    <p><strong>Closure does NOT apply (leave it OFF):</strong></p>
    <ul>
        <li><strong>A dilution or concentration series.</strong> The total amount
            deliberately changes between spectra — that's the point of the
            experiment.</li>
        <li><strong>A calibration series of standards</strong> at different known
            concentrations, for the same reason.</li>
        <li><strong>Samples at different total concentrations</strong>, or with
            varying path length, laser power, focus, or acquisition time — all
            scale the overall intensity, so the "total" is not constant.</li>
        <li><strong>A reaction where material is created, consumed or escapes</strong>
            — precipitation, evaporation, photobleaching, degradation, or product
            leaving the probed volume.</li>
        <li><strong>Any case where a significant contributing species is NOT in
            your component set</strong> — your components then can't sum to the
            whole, because part of the whole is missing from the model.</li>
        <li><strong>When you simply aren't sure.</strong> Off is the safe default:
            closure is a real constraint, not a cosmetic option.</li>
    </ul>

    <div class="note">
        <strong>What closure actually buys you.</strong> On a closed-system
        benchmark (DNA duplex melting) both settings recovered the pure spectra
        essentially perfectly — closure wasn't needed to <em>find</em> the answer.
        Its value is that the numbers come out already meaningful: with closure
        OFF the raw concentrations sat on an arbitrary scale (row sums ~4.5, e.g.
        2.51 / 2.02 for one spectrum) and only became interpretable after the
        display's "Normalize to 100%" rescaling; with closure ON the raw
        concentrations <em>are</em> mole fractions — 0.551 / 0.449 against a true
        0.548 / 0.452.
    </div>

    <div class="note">
        <strong>Closure vs "Normalize to 100% per spectrum" — not the same
        thing.</strong> Closure is a constraint applied <em>during</em> the fit:
        it changes which solution is found, and the pure spectra adapt to it.
        "Normalize to 100%" is a <em>display</em> rescaling applied <em>after</em>
        the fit: it never changes the fit, it just divides each spectrum's row by
        its own sum for viewing. If closure was off during the fit the raw
        concentrations don't naturally sum to a constant, so normalising them
        afterwards reshapes the profiles — which is exactly why the two can look
        different.
    </div>
    <hr>
    <hr>
    <h2>Exporting pure spectra to the main spectrum list</h2>
    <p>Unlike <strong>Saving data</strong> below (which writes to an Excel/Text
    file on disk), this adds one or more resolved pure spectra directly to
    the main spectrum list as ordinary spectra you can then process, plot, or
    combine with anything else in the app — click <strong>Export
    Pure Spectra&hellip;</strong>, choose which ones to include and a
    base label, then confirm.</p>
    <ul>
        <li><strong>Naming:</strong> each exported pure spectrum is named
            <code>&lt;base label&gt;_&lt;component number&gt;</code> — e.g.
            <code>MCR-ALS_1</code>, <code>MCR-ALS_2</code> for the default
            base label "MCR-ALS". If that name is already taken (e.g. you
            export twice), a numeric suffix is added automatically
            (<code>MCR-ALS_1_2</code>) so nothing is silently overwritten.</li>
        <li><strong>Which ones came from the same run:</strong> every pure
            spectrum exported together shares a <code>run_id</code> value in
            its metadata's Correction History entry. If you export from two
            different MCR-ALS runs, each run's pure spectra get their own,
            different <code>run_id</code> — the way to confirm two exported
            spectra are actually siblings from the same decomposition
            (rather than just happening to have adjacent numbers) is to
            check that their <code>run_id</code> matches, in each spectrum's
            own Metadata panel.</li>
        <li>Each exported spectrum's Correction History also records which
            component index it was (1-based), how many components the run
            used in total, the lack-of-fit, iterations used, convergence
            status, whether references were fixed, its own explained
            variance, and which original spectra fed into the decomposition
            — the same information available in the Pure Spectra tab,
            attached directly to the spectrum so it travels with it.</li>
    </ul>

    <div class="screenshot">
        <img src="$EXPORT_DIALOG" width="${EXPORT_DIALOG_W}" height="${EXPORT_DIALOG_H}" alt="Export Pure Spectra dialog: checkboxes for which pure spectra to include and a base label field" />
        <p class="caption">The Export Pure Spectra dialog: choose pure spectra and a base label.</p>
    </div>

    <h2>Saving data</h2>
    <p>The <strong>Save…</strong> button opens a dialog with the same shape
    as NMF/PCA/SVD's Save&hellip;:</p>
    <ul>
        <li><strong>File Format:</strong> Excel (.xlsx) or Text/CSV.</li>
        <li><strong>Include:</strong> Pure Spectra, Concentrations, and/or
            Info — tick any combination; all three are included by default.
            The Info sheet/section also records the lack-of-fit,
            iterations used, and whether the fit converged.</li>
        <li>For Excel, each included category becomes its own worksheet,
            with columns automatically widened so headers are fully visible
            the moment the file opens.</li>
        <li>For Text/CSV, choose a delimiter and decimal precision, and
            whether to combine everything into one file or write a
            separate file per category.</li>
    </ul>

    <div class="screenshot">
        <img src="$SAVE_DIALOG" width="${SAVE_DIALOG_W}" height="${SAVE_DIALOG_H}" alt="Save dialog: File Format, Include checkboxes, and delimiter/precision options" />
        <p class="caption">The Save dialog: file format, what to include, and CSV delimiter/precision options.</p>
    </div>

    <div class="warn">
        <strong>Not unique.</strong> Like NMF, MCR-ALS solutions depend on
        initialisation and constraints. Different, equally defensible
        settings can give different (but comparably low lack-of-fit)
        decompositions. Treat the resolved spectra as candidate pure
        components to be checked against chemical knowledge, not as a
        single definitive answer.
    </div>

    <hr>
    <h2>Test datasets with known ground truth</h2>
    <p>The application ships with <strong>22 synthetic datasets</strong> whose
    TRUE pure components and TRUE concentrations are known exactly. They are the
    only honest way to answer the question this whole tool struggles with — "is
    my decomposition actually <em>right</em>, not merely well-fitting?" — because
    with real data the truth isn't available to check against.</p>

    <p><strong>Open them from the menu:</strong>
    <span class="fm">Help &rarr; Spectra Analysis &amp; Visualization &rarr;
    Test datasets &rarr; Synthetic</span>. Each entry loads that workbook's
    mixture spectra straight into the application. The same menu has
    <em>Open datasets folder…</em>, which reveals the folder itself.</p>

    <p><strong>On disk:</strong> the datasets live in this folder:</p>
    <p><span class="fm">__DATASETS_DIR__</span></p>
    <p>To open that folder, use
    <span class="fm">Help &rarr; Test datasets &rarr; Synthetic &rarr;
    Open datasets folder&hellip;</span> in the application.
    A <span class="fm">README.md</span> in that folder documents everything
    below in more detail.</p>

    <h3>Every workbook has the same five sheets</h3>
    <table>
        <tr><th>Sheet</th><th>Contents</th></tr>
        <tr><td><span class="fm">Spectra</span></td>
            <td>The mixture spectra — first column is the x axis, then one column
                per spectrum. This is the sheet to analyse. (The Import dialog
                lets you pick any sheet, and "Import several sheets" lets you
                bring in more than one at once — pulling in
                <span class="fm">Pure_components</span> alongside is handy, since
                those can then be used directly as reference spectra.)</td></tr>
        <tr><td><span class="fm">Pure_components</span></td>
            <td>The TRUE pure-component spectra. Compare the resolved components
                against these.</td></tr>
        <tr><td><span class="fm">Concentrations</span></td>
            <td>The TRUE amount of each component in each spectrum (raw, and
                normalised to % per spectrum).</td></tr>
        <tr><td><span class="fm">Ground_truth</span></td>
            <td>Every true peak: component, centre, height, FWHM, sign.</td></tr>
        <tr><td><span class="fm">Info</span></td>
            <td>Design summary, recommended settings, and a sheet legend.</td></tr>
    </table>

    <h3>The datasets</h3>
    <table>
        <tr><th>Family</th><th>Files</th><th>Character</th><th>Settings to use</th></tr>
        <tr><td><strong>Raman</strong></td>
            <td><span class="fm">raman_{2,3,4}comp_{clean,noisy}.xlsx</span> (6)</td>
            <td>Many sharp bands, varied heights and widths. All positive.</td>
            <td>MCR-ALS with C and ST non-negativity ON, or NMF. Closure OFF.</td></tr>
        <tr><td><strong>UV/Vis</strong></td>
            <td><span class="fm">uvvis_{2,3}comp_{clean,noisy}.xlsx</span> (4)</td>
            <td>Only a few, <em>very broad</em> electronic bands. All positive.</td>
            <td>Same as Raman. NMF does especially well here (~0.99).</td></tr>
        <tr><td><strong>CD</strong></td>
            <td><span class="fm">cd_{2,3}comp_{clean,noisy}.xlsx</span> (4)</td>
            <td>Broad electronic bands, genuinely <strong>signed</strong> (+/&minus;).</td>
            <td>MCR-ALS with <strong>ST non-negativity OFF</strong>.
                <strong>NMF is not applicable.</strong> Closure OFF.</td></tr>
        <tr><td><strong>ROA / VCD</strong></td>
            <td><span class="fm">roa_{2,3}comp_{clean,noisy}.xlsx</span> (4)</td>
            <td>Many sharp vibrational bands like Raman, but <strong>signed</strong>
                (+/&minus;).</td>
            <td>MCR-ALS with <strong>ST non-negativity OFF</strong>.
                <strong>NMF is not applicable.</strong> Closure OFF.</td></tr>
        <tr><td><strong>Closed system</strong></td>
            <td><span class="fm">closed_dna_melting_{2,3}comp_{clean,noisy}.xlsx</span> (4)</td>
            <td>DNA duplex melting into single strands (and a three-state
                variant). Total material conserved, so the fractions sum to
                exactly 100% in every spectrum — see the
                <span class="fm">SUM_check</span> column.</td>
            <td>MCR-ALS with <strong>Closure ON</strong> — the one family where
                closure is physically correct.</td></tr>
    </table>
    <p>Within each family, the <em>clean</em> and <em>noisy</em> versions of a
    given component count share the same random seed, so their true components
    and true concentrations are <em>identical</em> — the only difference is the
    noise. That lets you see exactly what noise costs you.</p>

    <div class="note">
        <strong>What these datasets are really for.</strong> Measured against the
        known truth, the all-positive families (Raman, UV/Vis) recover their true
        components well. The <em>signed</em> families (CD, ROA/VCD) are the
        instructive ones: they fit to nearly <strong>0% lack-of-fit</strong> and
        yet recover the true components only partially — a perfect-looking fit
        that is nonetheless wrong. Anchoring known components in the
        <strong>Reference spectra</strong> panel lifts ROA recovery to ~0.99.
        That contrast — a flawless fit that is still the wrong answer, rescued by
        external knowledge — is the single most important thing to internalise
        before trusting either method on real data.
    </div>

    <h3>Comparing directly against ground truth (built into the dialog)</h3>
    <p>Rather than eyeballing the resolved components against the
    <span class="fm">Pure_components</span> sheet by hand, this dialog can overlay
    the TRUE curves directly on top of your fitted result and score how well they
    match. Because this only means anything for the synthetic datasets above — real
    spectra have no known-true decomposition to check against — it is deliberately
    <strong>not</strong> a button on the Settings panel. It lives in a right-click
    context menu instead, so it stays out of the way during ordinary use:</p>
    <ol>
        <li><strong>Right-click anywhere in the dialog</strong> (the plot, the
            settings panel, the tab bar — anywhere) and choose
            <span class="fm">Compare with ground truth (testing)&hellip;</span></li>
        <li>Pick the workbook that matches what you loaded and ran &mdash; e.g. if
            you imported and ran on <span class="fm">roa_2comp_clean.xlsx</span>,
            pick that same file in the picker. Picking a <em>different</em> dataset
            (wrong component count, wrong family, or clean vs. noisy) will still
            "work" numerically but the comparison will be meaningless, since it is
            no longer checking your fit against the data it was actually fitted to.</li>
    </ol>
    <p>Once loaded, four things change:</p>
    <ul>
        <li><strong>Pure Spectra tab</strong> — each TRUE pure-component spectrum is
            drawn as a <strong>dashed</strong> curve in the same colour as its
            best-matching fitted component (matching is automatic — see below), with
            the spectral similarity in its legend label.</li>
        <li><strong>Concentrations tab</strong> — each TRUE concentration profile is
            drawn as a <strong>dotted line with &times; markers</strong>, again in
            the matching fitted component's colour, so it reads clearly against
            Lines, Stacked bars, or Grouped bars alike.</li>
        <li><strong>Reconstruction tab</strong> — a third curve, the TRUE noise-free
            signal for whichever spectrum is selected, is added alongside Original
            and Reconstructed. This is a genuinely different comparison from
            Original vs. Reconstructed: it shows how close the fit gets to the real
            underlying signal, not just to the (possibly noisy) measurement.</li>
        <li>A new <strong>Ground Truth</strong> tab appears with a table (one row
            per fitted component: its best-matching TRUE component, spectral
            similarity, <strong>concentration r</strong>, and <strong>concentration
            RMSE (%)</strong>) and a summary including the <em>overall recovery
            score</em> — the mean matched spectral similarity, where 1.0 is a
            perfect match. Concentration r and RMSE are computed across your WHOLE
            series of spectra, not within a single measurement: for each matched
            pair of components, they compare how that component's concentration
            <em>changes from spectrum to spectrum</em> against how the TRUE
            component's concentration changes over the same series — see the note
            below for how to read them.</li>
    </ul>
    <p>Fitted and TRUE components are paired up automatically (by spectral shape,
    order-independent — it does not assume the K-th fitted component corresponds
    to the K-th true component), and concentrations are compared after normalising
    both to 100% per spectrum, since the raw concentration scale is arbitrary in
    NMF/MCR-ALS (a component's concentration column and its own spectrum can trade
    a multiplicative factor with no change to the fit) &mdash; the same convention
    already used by this dialog's own "Normalize to 100% per spectrum" option.</p>

    <h3>The four numbers, side by side</h3>
    <p>It's easy to mix these up since all four sound like "how good is my
    result", but each answers a genuinely different question:</p>
    <table>
        <tr><th>Metric</th><th>Compares</th><th>Needs ground truth?</th>
            <th>Blind to scale/offset?</th><th>What it's really telling you</th></tr>
        <tr><td><strong>Current run's lack of fit</strong></td>
            <td>Reconstructed data vs. your <em>measured</em> spectra</td>
            <td>No &mdash; always available, even on real data</td>
            <td>No &mdash; sensitive to absolute residual size</td>
            <td>How well the model reproduces what you measured. This is what
                the optimiser directly minimises.</td></tr>
        <tr><td><strong>Overall recovery score</strong></td>
            <td>Fitted pure-<em>spectrum</em> shapes vs. TRUE pure-spectrum
                shapes (mean matched cosine similarity)</td>
            <td>Yes &mdash; testing-only</td>
            <td>Yes &mdash; cosine similarity ignores overall scale</td>
            <td>Did you recover the right <em>spectral shapes</em>, regardless
                of their relative intensity.</td></tr>
        <tr><td><strong>Concentration r</strong></td>
            <td>One component's fitted concentration <em>trend</em> across all
                your spectra vs. its TRUE trend over the same series</td>
            <td>Yes &mdash; testing-only</td>
            <td>Yes &mdash; Pearson correlation ignores scale/offset</td>
            <td>Does it rise and fall in the right places, even if the
                absolute split between components is off.</td></tr>
        <tr><td><strong>Concentration RMSE (%)</strong></td>
            <td>The same two trends, point by point, after both are
                normalised to 100% per spectrum</td>
            <td>Yes &mdash; testing-only</td>
            <td>No &mdash; this is the one that catches an absolute-scale
                error the other three all miss</td>
            <td>How far off the actual percentage split is, in percentage
                points &mdash; the most literal-minded of the four.</td></tr>
    </table>
    <p>The organising pattern: lack-of-fit and RMSE are <em>magnitude</em>
    checks (they penalise being numerically wrong); the recovery score and r
    are <em>shape</em> checks (they only ask whether things move together,
    forgiving any consistent rescaling). A result can look perfect on either
    pair of "shape" metrics while still being wrong in an absolute sense —
    which is exactly why the report always shows all four rather than
    collapsing them into one score.</p>

    <div class="note">
        <strong>The recovery score and the lack-of-fit are different numbers and
        can disagree.</strong> A low lack-of-fit (a near-perfect fit to the
        <em>data</em>) does not guarantee a high recovery score (a correct match to
        the <em>true components</em>) &mdash; the signed datasets (CD, ROA/VCD)
        above are the clearest illustration of exactly that gap. The Ground Truth
        report shows both side by side for this reason.
    </div>
    <div class="note">
        <strong>Concentration r and RMSE also measure different things, and can
        disagree with each other.</strong> <strong>r</strong> (Pearson correlation)
        is scale/offset-independent — it only checks whether the fitted and TRUE
        profiles rise and fall <em>together</em> across your spectra, so it stays
        high even when the fitted values sit on a shifted or rescaled axis from the
        truth (and, in a two-component system, a poorly-separated component's
        profile is often still forced to trend opposite the other one, keeping r
        high almost by construction). <strong>RMSE</strong> is the actual
        point-by-point disagreement, in percentage points, after both are
        normalised to 100% per spectrum. A high r <em>together with</em> a high
        RMSE means "right trend, wrong absolute split" — the concentration-side
        symptom of the same non-uniqueness (rotational ambiguity) problem discussed
        above: MCR-ALS/NMF found a decomposition that fits the data and roughly
        tracks the right up/down pattern, but attributed the wrong absolute share
        to each component.
    </div>
    <div class="note">
        <strong>How to actually reduce rotational ambiguity</strong> (rather than
        just detect it): every constraint you can honestly impose narrows the set
        of equally-fitting solutions. The <strong>Reference spectra</strong> panel
        (anchoring one or more known pure-component shapes) works for any dataset
        and is the single most effective option available here — it's what lifts
        the ROA/VCD family's recovery from partial to ~0.99 above. This dialog's
        own <strong>Closure</strong> constraint (concentrations forced to sum to
        100% during the fit) can also help, and NMF does not offer it at all — but
        closure is only valid when your system is genuinely closed (total material
        conserved, species only convert into one another; see "When does Closure
        apply?" below). The Raman/UV&#8209;Vis/CD/ROA benchmark families here are
        deliberately <em>not</em> closed systems (their concentrations don't sum to
        a constant), so turning closure on for one of them would impose a false
        constraint and could make the true answer <em>less</em> reachable, not
        more — it is a remedy for the specific systems where it's physically
        justified, not a general-purpose ambiguity fix.
    </div>
    <div class="note">
        <strong>"Run N times, keep best" is valuable, but for a different reason
        than you might expect — it doesn't specifically target ground-truth
        recovery.</strong> NMF/MCR-ALS optimise a non-convex objective from a
        random or near-random starting point, so a single run can occasionally
        converge to a genuinely poor local minimum — a bad fit, not just an
        ambiguous one. Trying several random seeds and keeping the one with the
        lowest lack-of-fit is real, useful insurance against that failure mode,
        which is the much more common risk in practice. What it does
        <em>not</em> do is prefer a run that happens to recover the true
        components better, because on real data ground truth isn't known and
        lack-of-fit is the only signal available to rank runs by. Once several
        candidate runs are already fitting the data almost equally well, picking
        the single lowest-LOF one among them is effectively arbitrary with
        respect to which rotation of the solution it lands on — so it can
        occasionally recover the truth slightly better OR slightly worse than one
        plain run did, in either direction, and that direction can differ between
        MCR-ALS and NMF on the very same dataset. If you see that here, it isn't
        a bug: it's the clearest possible demonstration that minimising
        lack-of-fit (an optimisation problem, which more restarts do help with)
        and resolving rotational ambiguity (an identifiability problem, which
        restarts alone cannot fix — only real constraints like References or a
        correctly-applied Closure can) are genuinely different problems.
    </div>
    <p>Right-click again to <span class="fm">Change ground-truth dataset&hellip;</span>
    or <span class="fm">Clear ground-truth comparison</span>. The comparison is
    never saved anywhere: it lives only in the currently open dialog, so closing
    the dialog, or loading a new dataset / changing the spectra selection in the
    main window and reopening MCR-ALS, always starts with no comparison active.</p>

    <hr>
    <h2>Technical notes</h2>
    <p>The algorithm (alternating least squares): given the data matrix
    D (spectra &times; wavelengths), find C (concentrations) and ST
    (pure spectra) minimizing &Vert;D &minus; C&middot;ST&Vert;&sup2; by
    alternating:</p>
    <ol>
        <li>Solve for C given the current ST (non-negative least squares
            per spectrum row, if "Non-negative concentrations" is on;
            ordinary least squares otherwise).</li>
        <li>If Closure is on, project each row of C onto "sums to 1"
            before continuing.</li>
        <li>Solve for ST given the new C (non-negative least squares per
            wavelength column, if "Non-negative spectra" is on; ordinary
            least squares otherwise).</li>
        <li>Rescale each component's ST row to unit norm, compensating in
            C, to keep the scale ambiguity between C and ST from
            drifting (skipped when Closure is on, which already pins the
            scale down its own way).</li>
        <li>Repeat until the lack-of-fit stops improving by more than the
            convergence tolerance, or Max Iterations is reached.</li>
    </ol>
    <p>Lack of fit: 100 &times; &radic;(&Sigma;(D&minus;C&middot;ST)&sup2;
    / &Sigma;D&sup2;) — the same formula used throughout this dialog and
    in NMF's status line, for direct comparability between the two
    methods.</p>
    <div class="note">
        <strong>Why lack of fit plateaus well above 0% on real data:</strong>
        baseline correction removes a slowly-varying background, not the
        point-to-point shot/detector noise riding on every peak — and no
        smooth, non-negative low-rank model can fit genuine random noise,
        since it isn't a pattern shared across spectra. On real, noisy
        maps that noise floor often accounts for most of a lack-of-fit
        that stalls at, say, 15&ndash;25% once the first few components
        have already captured the actual chemistry (check each
        component's EV% for confirmation) — adding more components beyond
        that point mostly chases noise rather than finding more chemistry,
        and this is not by itself a sign of a poor fit or a bug. See
        NMF's help page ("What 'Lack of fit' means") for the full
        explanation, which applies identically here since both methods
        share this formula.
    </div>
    <p>Background: Tauler, R. "Multivariate curve resolution applied to
    second order data." <em>Chemometrics and Intelligent Laboratory
    Systems</em> 30 (1995): 133-146 — the original MCR-ALS formulation
    this implementation follows the spirit of, though this is an
    independent implementation, not a port of any specific published
    code.</p>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies
    everywhere this dialog shows a spectrum label: the Concentrations
    tab's x-axis labels (when "Use spectrum index" is unchecked), the
    Reconstruction tab's spectrum-selector list and plot title, and the
    Fit Quality tab's per-spectrum bar chart. It only affects what is
    <em>displayed</em> — spectrum identity, and any name written into a
    new or exported spectrum, is always the full original label. Toggling
    the main window's Shorten names checkbox has no effect on this
    dialog.</p>

    </body></html>
    """)

    return _fill_dataset_paths(html.safe_substitute(images))
