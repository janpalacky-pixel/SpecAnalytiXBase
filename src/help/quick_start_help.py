# src/help/quick_start_help.py

"""
Help content for the Quick Start page — a short, single-page orientation
that sits above the full User Guide in the Help menu. It links out to the
User Guide, the Developer Guide, and every operation/analysis topic's own
help page rather than duplicating their content, so it stays short and
never goes stale relative to them.
"""

import os
import struct
from pathlib import Path

from src.modules.utils.resource_path import resource_path


# Photos for the "Questions & Contact" section — same directory/resolution
# approach as every screenshot-bearing help page (see
# svd_interpolation_help.py's _resolve_screenshot_uris for the full
# rationale: resource_path() resolves correctly both from source and from
# a PyInstaller-frozen build; the whole resources/ tree is bundled
# wholesale — see BuildInstaller.bat / SpecAnalytiXBase.spec — so nothing
# extra needs adding there for this).
#
# Each entry is a base filename with no extension — _find_photo() tries
# each of _PHOTO_EXTENSIONS in turn, so dropping in either a .jpg or a
# .png under either name is enough; no code change needed to add the
# actual pictures.
_PHOTO_DIR = os.path.join("resources", "images", "photos")
_PHOTO_BASENAMES = {
    "JAN_PHOTO":   "jan_palacky",
    "GROUP_PHOTO": "group_photo",
}
_PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png")

# Cap displayed width — these are portrait/group photos next to a short
# contact list, not full-width screenshots.
_MAX_PHOTO_WIDTH = 220


def _png_size(path):
    """Return (width, height) in pixels for a PNG, read from its IHDR
    chunk — avoids needing Pillow just to check dimensions. Same
    implementation as svd_interpolation_help.py's _png_size."""
    with open(path, "rb") as f:
        header = f.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a readable PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def _jpeg_size(path):
    """Return (width, height) in pixels for a JPEG, by scanning its
    marker segments for the first Start-Of-Frame (SOF) marker — the only
    one that carries image dimensions. Minimal, dependency-free — no
    Pillow needed, matching this codebase's existing PNG-only helper's
    reasoning, just extended to cover JPEG too since a phone/camera photo
    is far more likely to be a .jpg than a .png."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        raise ValueError(f"Not a readable JPEG: {path}")
    i = 2
    # SOF markers (baseline/progressive/etc.) — excludes DHT/DAC (0xC4/0xCC),
    # which share the 0xC0-0xCF range but aren't SOF markers.
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                   0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in sof_markers:
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        if marker == 0xD8 or 0xD0 <= marker <= 0xD9:
            # Markers with no payload (SOI/RST*/EOI) — advance past the
            # marker only, there's no length field to read.
            i += 2
            continue
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg_len
    raise ValueError(f"No SOF marker found in JPEG: {path}")


def _find_photo(base_name):
    """Return the resolved absolute path to the first existing file named
    *base_name* + one of _PHOTO_EXTENSIONS under _PHOTO_DIR, or None if
    none of them exist yet (photos not added yet — see _photo_html_block,
    which falls back to a placeholder instead of a broken <img> in that
    case)."""
    for ext in _PHOTO_EXTENSIONS:
        candidate = resource_path(os.path.join(_PHOTO_DIR, base_name + ext))
        if os.path.isfile(candidate):
            return candidate
    return None


def _photo_html_block(base_name, alt_text):
    """Build the <img> (or placeholder, if the photo file doesn't exist
    yet) HTML for one contact photo — resolved once per help-page build,
    same as every other screenshot on other help pages, so newly dropped-in
    photos show up the next time this page is opened with no code change."""
    path = _find_photo(base_name)
    if path is None:
        # No photo yet — a light placeholder instead of a broken image
        # icon, so the page still reads cleanly before photos are added.
        # Once a file named e.g. resources/images/photos/jan_palacky.jpg
        # (or .jpeg/.png) exists, this block is replaced automatically.
        return (
            '<div style="display:inline-block; width:' + str(_MAX_PHOTO_WIDTH) + 'px; '
            'height:' + str(_MAX_PHOTO_WIDTH) + 'px; background:#F4F5F7; '
            'border:1px dashed #B0B8C8; border-radius:6px; text-align:center; '
            'vertical-align:top; color:#7f8c8d; font-size:0.85em; padding-top:90px;">'
            'photo not yet added</div>'
        )
    try:
        if path.lower().endswith(".png"):
            native_w, native_h = _png_size(path)
        else:
            native_w, native_h = _jpeg_size(path)
        display_w = min(native_w, _MAX_PHOTO_WIDTH)
        display_h = round(native_h * (display_w / native_w))
    except (OSError, ValueError):
        display_w, display_h = _MAX_PHOTO_WIDTH, _MAX_PHOTO_WIDTH
    uri = Path(path).as_uri()
    return (
        f'<img src="{uri}" width="{display_w}" height="{display_h}" alt="{alt_text}" '
        'style="border-radius:6px; border:1px solid #dee2e6; vertical-align:top;" />'
    )


def get_quick_start_help_title():
    return "Quick Start"


def get_quick_start_help_content():
    jan_photo_html = _photo_html_block(_PHOTO_BASENAMES["JAN_PHOTO"], "Jan Palacky")
    group_photo_html = _photo_html_block(
        _PHOTO_BASENAMES["GROUP_PHOTO"], "Biophysics of Nucleic Acids research group")
    content = """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1976D2; margin-top: 28px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            h3    { color: #F57C00; margin-top: 18px; }
            a     { color: #1976D2; }
            .tip      { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .info     { background-color: #e3f2fd; padding: 10px; margin: 8px 0; border-left: 4px solid #2196f3; border-radius: 0 5px 5px 0; }
            table { width: 100%; border-collapse: collapse; margin: 10px 0; }
            th    { background-color: #E3EAF4; color: #1976D2; padding: 7px 10px; text-align: left; }
            td    { padding: 6px 10px; border-bottom: 1px solid #E0E0E0; }
            tr:nth-child(even) { background-color: #F8F9FB; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace; }
        </style>
    </head>
    <body>

        <h1>Quick Start</h1>

        <p>A short orientation: how to get from "just opened the app" to a
        finished analysis, with links to the full help page for every step
        along the way. For the complete picture, see the
        <a href="help://user_guide">User Guide</a>; if you're reading or
        extending the source code itself, see the
        <a href="help://developer_guide">Developer Guide</a>. Need to
        install, reinstall, or run the application itself from source? See
        <a href="help://installation">Installation</a>.</p>

        <h2>1. The Basic Workflow</h2>
        <ol>
            <li><b>Import</b> one or more spectrum files — <b>File &rarr; Import</b>,
                drag and drop onto the window, or the <b>Import</b> toolbar button.</li>
            <li><b>Select</b> the spectra you want to work with in the list on the left
                (click, Shift+click, Ctrl+click, or drag — see the User Guide's
                <a href="help://user_guide#selection">Spectrum Selection</a> section).</li>
            <li><b>Process</b> them with one or more operations from the
                <b>Spectra Processing</b> panel/menu (baseline correction, smoothing,
                normalization, ...) — each one previews before you commit, and every
                commit is recorded in <b>Operations History</b> so you can always step
                back.</li>
            <li><b>Analyze / visualize</b> with a tool from the
                <b>Spectra Analysis &amp; Visualization</b> menu (SVD, PCA, NMF,
                MCR-ALS, Cluster Analysis, ...).</li>
            <li><b>Save</b> your results — <b>File &rarr; Save</b> — as text, Excel,
                GRAMS (.spc), or a full session snapshot.</li>
        </ol>
        <div class="tip">
            <b>Everything below is a plain link to that topic's own full help
            page</b> — this page intentionally stays short. Every dialog also has
            its own orange/blue <b>Help</b> button that opens the exact same page
            directly, so you never have to come back here to find it again.
        </div>

        <h2 id="import">2. Importing Data</h2>
        <p>The Import dialog reads plain-text (<code>.txt</code>, <code>.csv</code>,
        <code>.dat</code>), Excel (<code>.xlsx</code>, <code>.xls</code>,
        <code>.xlsm</code>), and several instrument-specific binary formats
        (SPE, SPC, JWS) directly, with a live preview and auto-detection of
        delimiter, decimal separator, and header row so most files import
        correctly with no manual setup at all. For anything auto-detection
        gets wrong, every setting in the dialog is fully explained in one
        place:</p>
        <p><a href="help://import"><b>&#128214; Import — full help</b></a></p>

        <h2>3. Spectra Processing Operations</h2>
        <p>Operations that take your spectra and produce corrected/transformed
        spectra — baseline removal, smoothing, normalization, and similar. Reached
        from the <b>Spectra Processing</b> panel or menu; every one previews before
        you commit and is fully undoable via Operations History.</p>

        <h3>Baseline Correction</h3>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Manual Baseline</td><td>Click points on the plot to define a
                baseline, interpolated between them</td>
                <td><a href="help://manual_baseline">Open help</a></td></tr>
            <tr><td>Automated Baseline (ALS / airPLS / arPLS / iarPLS / psalsa / I-ModPoly / Morphological)</td><td>Seven automatic baseline
                algorithms (Asymmetric Least Squares, adaptive iteratively
                reweighted PLS, asymmetrically reweighted PLS, an improved arPLS fixing its small-peak overestimation, a peak-decay variant of ALS, a global polynomial fit with iterative peak rejection, or parameter-free adaptive morphological opening), with one-click region-shortcut presets (e.g. water band)</td>
                <td><a href="help://automated_baseline">Open help</a></td></tr>
            <tr><td>SNIP Baseline</td><td>Statistics-sensitive Non-linear Iterative
                Peak-clipping — another automatic baseline estimator</td>
                <td><a href="help://snip_baseline">Open help</a></td></tr>
            <tr><td>SVD Background</td><td>Baseline/noise removal by
                reconstructing from a chosen subset of SVD components</td>
                <td><a href="help://svd_background">Open help</a></td></tr>
        </table>

        <h3>Smoothing</h3>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>SG-Smoothing</td><td>Savitzky-Golay filtering; can also
                compute smoothed derivatives</td>
                <td><a href="help://sg_smoothing">Open help</a></td></tr>
            <tr><td>FFT Denoising</td><td>Removes noise by filtering in the
                frequency domain, including targeted mains-hum removal</td>
                <td><a href="help://fft_denoising">Open help</a></td></tr>
        </table>

        <h3>Data Manipulation</h3>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Define Spectral Range</td><td>Crop to an x-range, and/or
                linearise onto a common x-axis (needed before Combine/Calculator)</td>
                <td><a href="help://data_range">Open help</a></td></tr>
            <tr><td>Combine Spectra</td><td>Merge, average, or otherwise combine
                several spectra into one</td>
                <td><a href="help://combine_spectra">Open help</a></td></tr>
            <tr><td>Interactive Subtraction</td><td>Subtract a reference spectrum
                with a live, draggable scale factor</td>
                <td><a href="help://interactive_subtraction">Open help</a></td></tr>
            <tr><td>X-axis Alignment</td><td>Corrects small x-axis shifts/drift
                between spectra that should share one axis</td>
                <td><a href="help://xaxis_alignment">Open help</a></td></tr>
            <tr><td>SVD Interpolation</td><td>Interpolates spectra to new
                parameter values using an SVD-based model</td>
                <td><a href="help://svd_interpolation">Open help</a></td></tr>
        </table>

        <h3>Axis &amp; Unit Conversion</h3>
        <p>Operations that convert or rescale the values on an axis into
        different units, rather than removing/adding data or correcting shape.</p>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Spectral Calculator</td><td>Arithmetic between spectra
                (subtraction, ratios, custom formulas)</td>
                <td><a href="help://spectral_calculator">Open help</a></td></tr>
            <tr><td>Normalization</td><td>Intensity normalization (max, area, ...)
                and scatter-correction methods (SNV, MSC)</td>
                <td><a href="help://normalization">Open help</a></td></tr>
            <tr><td>CD Unit Conversion</td><td>Raw mdeg CD signal &rarr; molar/
                mean-residue ellipticity, &Delta;&epsilon;, or &Delta;A</td>
                <td><a href="help://cd_unit_conversion">Open help</a></td></tr>
            <tr><td>X-axis Unit Conversion</td><td>Wavelength (nm) &harr;
                wavenumber (cm&#8315;&sup1;) &harr; energy (eV) &harr; frequency (Hz)</td>
                <td><a href="help://xaxis_unit_conversion">Open help</a></td></tr>
            <tr><td>Mean-Center Spectra (Dataset)</td><td>Subtracts the ensemble
                average spectrum of a selected batch from every spectrum in it</td>
                <td><a href="help://mean_centering">Open help</a></td></tr>
        </table>

        <h3>Spike Removal</h3>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Spike Removal</td><td>Removes single-point spikes (cosmic
                rays, detector glitches) from individual spectra</td>
                <td><a href="help://spike_removal">Open help</a></td></tr>
            <tr><td>Cosmic Ray Removal (Cross-spectrum)</td><td>Detects and
                removes spikes by comparing across a whole set of spectra</td>
                <td><a href="help://cosmic_ray">Open help</a></td></tr>
        </table>

        <h3>Resolution</h3>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Resolution Enhancement</td><td>Wiener deconvolution to sharpen
                overlapping peaks</td>
                <td><a href="help://resolution">Open help</a></td></tr>
        </table>

        <h3>Batch Pipeline</h3>
        <table>
            <tr><th>Operation</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Batch Pipeline Replay</td><td>Capture a named sequence of
                operations from Operations History and replay it on any spectra
                selection later, in this session or a future one</td>
                <td><a href="help://batch_pipeline">Open help</a></td></tr>
        </table>

        <h2>4. Spectra Analysis &amp; Visualization</h2>
        <p>Tools that extract information from a set of spectra rather than
        transforming the spectra themselves — decomposition, clustering,
        matching, quantitative measurements. Reached from the
        <b>Spectra Analysis &amp; Visualization</b> menu.</p>

        <h3>Visualization</h3>
        <table>
            <tr><th>Method</th><th>What it does</th><th>Help</th></tr>
            <tr><td>SVD Analysis</td><td>Singular Value Decomposition —
                subspectra, coefficients, diagnostics, reconstruction</td>
                <td><a href="help://svd_analysis">Open help</a></td></tr>
            <tr><td>PCA Scores &amp; Loadings</td><td>Principal Component
                Analysis — sample clustering, outlier detection, loadings</td>
                <td><a href="help://pca_scores">Open help</a></td></tr>
            <tr><td>NMF</td><td>Non-negative Matrix Factorisation — components
                and concentrations constrained to be non-negative</td>
                <td><a href="help://nmf">Open help</a></td></tr>
            <tr><td>MCR-ALS</td><td>Multivariate Curve Resolution (Alternating
                Least Squares) — component spectra and concentration profiles</td>
                <td><a href="help://mcr_als">Open help</a></td></tr>
            <tr><td>Cluster Analysis</td><td>K-Means, Hierarchical, or DBSCAN
                clustering of your spectra</td>
                <td><a href="help://cluster_analysis">Open help</a></td></tr>
            <tr><td>2D Map</td><td>False-colour spatial map from a
                hyperspectral Raman/IR scan &mdash; one pixel per spectrum</td>
                <td><a href="help://map2d">Open help</a></td></tr>
            <tr><td>2D Correlation (2D-COS)</td><td>Synchronous/asynchronous
                two-dimensional correlation spectroscopy</td>
                <td><a href="help://two_d_correlation">Open help</a></td></tr>
            <tr><td>PLS / PLS-DA</td><td>Calibration model (regression) or
                classifier (PLS-DA) built from spectra with known values,
                predicts unknowns</td>
                <td><a href="help://pls">Open help</a></td></tr>
        </table>

        <h3>Data Analysis</h3>
        <table>
            <tr><th>Method</th><th>What it does</th><th>Help</th></tr>
            <tr><td>Peak Fitting</td><td>Fits peak shapes (Gaussian/Lorentzian/
                Voigt, ...) to extract position, height, width, area</td>
                <td><a href="help://peak_fitting">Open help</a></td></tr>
            <tr><td>Band Ratio / Peak Area Calculator</td><td>Tracks the ratio
                or difference between two bands across a spectral series</td>
                <td><a href="help://band_ratio">Open help</a></td></tr>
            <tr><td>Reference Library Matching</td><td>Scores your spectra
                against a reference library by similarity metric</td>
                <td><a href="help://reference_matching">Open help</a></td></tr>
            <tr><td>Melting Curve Analysis</td><td>Fits thermal transitions
                (T<sub>m</sub>, van't Hoff / Arrhenius) from a temperature series</td>
                <td><a href="help://melting_curve">Open help</a></td></tr>
            <tr><td>Isosbestic / Isodichroic Point Detection</td><td>Finds
                x-axis point(s) where a spectral series (titration, temperature,
                time, ...) all cross — the signature of a clean two-species process</td>
                <td><a href="help://isosbestic_point">Open help</a></td></tr>
            <tr><td>Kinetics Fitting</td><td>Fits exponential decay/rise
                rate constant(s) from a time series, single-wavelength or
                global (shared rates + Decay-Associated Spectra)</td>
                <td><a href="help://kinetics_fitting">Open help</a></td></tr>
            <tr><td>QC / Outlier Detection</td><td>PCA-based check of a
                batch of spectra against each other — flags spectra that
                are unusual (Hotelling T²) or don't fit the batch's
                spectral shape at all (Q-residual)</td>
                <td><a href="help://qc_outlier">Open help</a></td></tr>
        </table>
        <p>Most of the tools above (PLS/PLS-DA, Band Ratio, Reference Library
        Matching, Isosbestic Point Detection, Kinetics Fitting, QC/Outlier
        Detection) have an <strong>Export PDF&hellip;</strong> button next to
        Export CSV — a self-contained report with the plot, settings, and
        results table. Melting Curve Analysis has the same report under its
        <strong>Fit Details</strong> menu instead.</p>

        <h2 id="save">5. Saving Your Data</h2>
        <p>Save your (processed) spectra as delimited text, Excel, or the
        binary GRAMS (<code>.spc</code>) format — or save a full session
        <b>Snapshot</b> to pick up exactly where you left off, spectra and
        Operations History included. <b>File &rarr; Save</b> opens the Save
        Options dialog:</p>
        <p><a href="help://save"><b>&#128214; Save — full help</b></a></p>

        <h2 id="test-data">6. Try It With Test Datasets</h2>
        <p><b>Help &rarr; Test datasets</b> opens a submenu of small, ready-made
        workbooks straight into the application — no importing required. The
        <b>Synthetic</b> ones are especially useful while learning: their true
        number of components and concentration profiles are known by
        construction (kept on the workbook's other sheets), so you can run
        SVD, NMF, or MCR-ALS against them and check your result against the
        known ground truth before trusting the same tool on your own data. See
        the User Guide's
        <a href="help://user_guide#test-datasets">Test Datasets</a> section for
        what each one is designed to demonstrate.</p>

        <h2 id="contact">7. Questions &amp; Contact</h2>
        <p>Collaboration, bug report, etc.</p>
        <table style="width:auto; border-collapse:separate;">
            <tr>
                <td style="border:none; padding-right:16px; vertical-align:top;">__JAN_PHOTO__</td>
                <td style="border:none; padding-right:16px; vertical-align:top;">__GROUP_PHOTO__</td>
                <td style="border:none; vertical-align:top;">
                    <ul style="margin-top:0;">
                        <li>Email: <a href="mailto:janpalacky@ibp.cz">janpalacky@ibp.cz</a></li>
                        <li>Research group page:
                            <a href="https://www.ibp.cz/en/research/departments/biophysics-of-nucleic-acids/research-profile">
                            Biophysics of Nucleic Acids &mdash; Institute of Biophysics</a></li>
                    </ul>
                </td>
            </tr>
        </table>
        <div class="info">
            Reading or extending the source code itself? See the
            <a href="help://developer_guide">Developer Guide</a> — architecture,
            conventions, and the same
            <a href="help://developer_guide#contact">Questions &amp; Contact</a>
            details as above.
        </div>

    </body>
    </html>
    """
    content = content.replace("__JAN_PHOTO__", jan_photo_html)
    content = content.replace("__GROUP_PHOTO__", group_photo_html)
    return content
