# src/help/map2d_help.py
"""Help content for the 2D Spectral Map dialog."""

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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "map2d")

_SCREENSHOT_FILES = {
    "OVERVIEW":            "dialog_overview.png",
    "MAP_DIMENSIONS":      "map_dimensions.png",
    "SUGGEST_DIALOG":      "suggest_dialog.png",
    "TYPE_INTENSITY":      "map_type_intensity.png",
    "TYPE_ARITHMETIC":     "map_type_arithmetic.png",
    "TYPE_SVD":            "map_type_svd.png",
    "SVD_SPECTRUM_PANEL":  "svd_spectrum_panel.png",
    "SVD_FULL_RANGE":      "svd_full_spectrum_range.png",
    "TYPE_PCA":            "map_type_pca.png",
    "PCA_SPECTRUM_PANEL":  "pca_spectrum_panel.png",
    "MULTI_MAP_RESULT":    "svd_multi_map_result.png",
    "TYPE_NMF":            "map_type_nmf.png",
    "TYPE_MCR":            "map_type_mcr.png",
    "NMF_MCR_SPECTRUM_PANEL": "nmf_mcr_spectrum_panel.png",
    "REF_SPECTRA_PANEL":   "ref_spectra_panel.png",
    "TYPE_CLUSTER":        "map_type_cluster.png",
    "CLUSTER_MAP_RESULT":  "cluster_map_result.png",
    "CONFIGURE_RANGE":     "configure_range_dialog.png",
    "DISPLAY_OPTIONS":     "display_options.png",
    "SPECTRUM_PANEL":      "spectrum_panel.png",
    "HOVER_TOOLTIP":       "hover_tooltip.png",
    "ROI_MENU":            "roi_menu.png",
    "ROI_RECTANGLE":       "roi_drawn_rectangle.png",
    "ROI_COMPARISON":      "roi_comparison_stats.png",
    "ROI_VIEWER":          "roi_spectra_viewer.png",
    "TYPE_RGB":            "map_type_rgb.png",
    "RGB_OVERLAY_RESULT":  "rgb_overlay_result.png",
}

# Cap displayed screenshot width at this many pixels — see
# svd_background_help.py for why explicit width/height attributes are used
# instead of relying on CSS to constrain image size.
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


def get_map2d_help_title():
    return "2D Spectral Map – Help"


def get_map2d_help_content():
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders), not str.format()/f-strings — the
    # CSS block below is full of literal { } braces that would collide with
    # .format()-style placeholders.
    help_template = Template("""
<html><head><style>
    body  { font-family: Arial, sans-serif; margin: 16px; line-height: 1.55; font-size: 13px; }
    h1    { color: #1565C0; border-bottom: 2px solid #1565C0; padding-bottom: 4px; }
    h2    { color: #2E7D32; margin-top: 20px; }
    h3    { color: #E65100; margin-top: 12px; margin-bottom: 3px; }
    .cat  { background: #f5f5f5; padding: 9px 13px; margin: 6px 0; border-radius: 5px; }
    .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32; padding: 8px 12px; margin: 7px 0; }
    .note { background: #E3F2FD; border-left: 4px solid #1565C0; padding: 8px 12px; margin: 7px 0; }
    .warn { background: #FFF3E0; border-left: 4px solid #E65100; padding: 8px 12px; margin: 7px 0; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; }
    th    { background: #E3F2FD; text-align: left; padding: 5px 8px; }
    td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
    ul,ol { padding-left: 18px; } li { margin: 3px 0; }
    hr    { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
    .screenshot { margin: 12px 0; text-align: center; }
    .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
    .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
</style></head><body>

<h1>2D Spectral Map</h1>

<p>The <b>2D Map</b> tool converts a flat collection of spectra into a
two-dimensional colour-coded image where each pixel corresponds to one spectrum.
It is particularly useful for hyperspectral Raman or IR mapping experiments
recorded on a regular (x, y) grid.</p>

<div class="screenshot">
    <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="2D Spectral Map dialog overview" />
    <p class="caption">The full dialog: map controls on the left, map view and spectrum panel on the right.</p>
</div>

<div class="note">
<b>Prerequisite:</b> Load and optionally pre-process your spectra in the main
pipeline before opening this tool. Select the spectra you want to map using the
spectrum list on the left of the main window. All preprocessing (baseline,
normalisation, data range clipping, smoothing) should be done before entering
the 2D Map — the map uses whatever spectra you pass in as-is.
</div>

<hr>
<h2>1 — Map Dimensions</h2>

<div class="cat">
<p>Enter the physical scan dimensions in the <b>Rows × Cols</b> spinboxes.
<b>Rows × Cols must equal the total number of selected spectra.</b>
A green tick appears when the product is valid; a red message shows
the discrepancy otherwise. Spectra are placed row-by-row (C order).</p>
<p>The map redraws automatically as soon as valid dimensions are entered
(for Intensity, Map arithmetic and Cluster overlay — SVD, NMF and
MCR-ALS still need <b>Update Map</b> pressed explicitly).</p>

<div class="note">
If every selected spectrum carries the map's own row/col size (true for
MAT/WITec map imports — see the 2D Map help section of the Import dialog),
the dialog reads it automatically: Rows × Cols are filled in and the map
is drawn as soon as the dialog opens, with no need to enter dimensions or
use Suggest… at all. This only happens once, at startup — changing
settings afterward (e.g. switching to NMF) still needs Update Map pressed
as usual. A plain text/column-format map import doesn't carry this
information, so it falls back to the manual entry described below.
</div>

<div class="screenshot">
    <img src="$MAP_DIMENSIONS" width="$MAP_DIMENSIONS_W" height="$MAP_DIMENSIONS_H" alt="Map Dimensions group: Rows x Cols spinboxes and validity message" />
    <p class="caption">The Map Dimensions group, with the Rows × Cols spinboxes and validity indicator.</p>
</div>

<h3>Suggest… button</h3>
<p>Opens a selectable list of all valid integer (rows, cols) factor pairs.
The pair whose aspect ratio is closest to 1:1 is pre-selected.
Double-clicking or pressing OK applies the chosen pair immediately.</p>

<div class="screenshot">
    <img src="$SUGGEST_DIALOG" width="$SUGGEST_DIALOG_W" height="$SUGGEST_DIALOG_H" alt="Suggest dimensions dialog listing valid factor pairs" />
    <p class="caption">The "Suggest…" dialog, listing valid (rows, cols) factor pairs.</p>
</div>
</div>

<hr>
<h2>2 — Map Type</h2>

<p>Select a map type using the radio buttons. Switching between
<b>Intensity metric</b>, <b>Map arithmetic</b>, and <b>Cluster overlay</b>
redraws the map instantly. <b>SVD</b>, <b>PCA</b>, <b>NMF</b> and
<b>MCR-ALS</b> redraw instantly too when you switch to (or back to) a kind
that has already been fitted for the current settings — the existing fit
is simply redrawn from cache, with no re-fit and no need to press
<b>Update Map</b>. Fitting is only needed the first time a kind is used,
or again after a setting that actually invalidates that fit — its
spectral range, its component count (NMF/MCR-ALS), its reference
spectra, or (NMF/MCR-ALS only) its own fit-control settings such as
NMF's <b>Init.</b>/<b>Max iter.</b> or MCR-ALS's <b>Max iter.</b>/
<b>Non-neg. C</b>/<b>Non-neg. ST</b>/<b>Closure</b> — in which case
<b>Update Map</b> is required, exactly as before.
<b>RGB overlay</b> never needs <b>Update Map</b> at all: composing it from
already-fitted components is cheap, so it always redraws live.</p>

<h3>◉ Intensity metric</h3>
<div class="cat">
<p>Computes one scalar value per spectrum within the configured <b>Band</b>
range and maps it as a pixel colour.</p>

<div class="screenshot">
    <img src="$TYPE_INTENSITY" width="$TYPE_INTENSITY_W" height="$TYPE_INTENSITY_H" alt="Map Type panel with Intensity metric selected" />
    <p class="caption">Map Type panel in Intensity metric mode, with the Metric dropdown and Band controls.</p>
</div>

<table>
<tr><th>Metric</th><th>Description</th></tr>
<tr><td><b>Integral</b></td><td>Area under the range-filtered spectrum (trapezoidal rule). Best for concentration mapping.</td></tr>
<tr><td><b>Mean</b></td><td>Average y-value over the range.</td></tr>
<tr><td><b>Variance</b></td><td>Spectral variance within the range. Highlights heterogeneous or broadened bands.</td></tr>
<tr><td><b>Peak intensity</b></td><td>Maximum y-value in the range.</td></tr>
<tr><td><b>Peak position</b></td><td>x-value at the intensity maximum. Maps band shift across the sample.</td></tr>
<tr><td><b>FWHM</b></td><td>Full width at half maximum of the dominant peak. Returns blank/NaN for a pixel where the peak sits close enough to the edge of the selected range that the spectrum never actually descends to half-maximum on one side — rather than a falsely narrow width computed from an incomplete peak. Widen the range if too many pixels come back blank.</td></tr>
<tr><td><b>Baseline-corrected integral</b></td><td>Area above the chord connecting the range endpoints.</td></tr>
<tr><td><b>Intensity at x</b></td><td>Interpolated intensity at a single x-value. Enter the x-value in the <b>x:</b> spinbox. No range configuration needed.</td></tr>
</table>

<div class="note">
<b>Range-based vs. single-point.</b> Every metric above except
<b>Intensity at x</b> computes its value from every point within the
configured <b>Band</b> range — Mean and Integral average/sum across it,
Peak intensity/position and FWHM find a feature within it, and so on.
<b>Intensity at x</b> is different: it linearly interpolates the full
spectrum at exactly the one x-value you enter, a single point rather
than an average over a range or its neighboring points — so it is more
sensitive to noise at that exact position than the other options. If
you want noise averaged out at a specific feature, use <b>Mean</b> (or
<b>Integral</b>) over a narrow range centered on it instead. Click the
small orange <b>?</b> button next to the Metric dropdown (visible in
this mode) for this same explanation without leaving the dialog.</div>

<p>Changing the metric immediately redraws the map.</p>
</div>

<h3>◉ Map arithmetic</h3>
<div class="cat">
<p>Computes the same metric for two independently configured bands (A and B)
and combines them pixel-wise. Useful for band-ratio maps that highlight
stoichiometric variations.</p>

<div class="screenshot">
    <img src="$TYPE_ARITHMETIC" width="$TYPE_ARITHMETIC_W" height="$TYPE_ARITHMETIC_H" alt="Map Type panel with Map arithmetic selected" />
    <p class="caption">Map Type panel in Map arithmetic mode: Configure Band A…/B… buttons and the Operation dropdown.</p>
</div>

<table>
<tr><th>Operation</th><th>Use case</th></tr>
<tr><td><b>A / B</b></td><td>Ratio map — most common for Raman phase mapping.</td></tr>
<tr><td><b>A − B</b></td><td>Difference map.</td></tr>
<tr><td><b>A + B</b></td><td>Sum map.</td></tr>
<tr><td><b>A × B</b></td><td>Product map.</td></tr>
</table>
<p>Click <b>Configure Band A…</b> and <b>Configure Band B…</b> to define
the spectral range for each band independently. The map redraws
automatically after configuring either band.</p>
<p>For <b>Intensity at x</b> metric in arithmetic mode, two separate
x-value spinboxes appear: <b>x₁ (Band A)</b> and <b>x₂ (Band B)</b>.
No range configuration buttons are shown — point interpolation needs no range.</p>
<div class="note">
<b>A/B ratio:</b> when x₁ = x₂ the ratio is exactly 1.0 for every pixel
(both bands interpolate from the same full spectrum).
</div>
</div>

<h3>◉ SVD</h3>
<div class="cat">
<p>Performs Singular Value Decomposition on the range-filtered spectra and
maps the coefficient vector V<sub>k</sub> as pixel values.</p>

<div class="screenshot">
    <img src="$TYPE_SVD" width="$TYPE_SVD_W" height="$TYPE_SVD_H" alt="Map Type panel with SVD selected" />
    <p class="caption">Map Type panel in SVD mode: Browse-component selector, Invert, Multi-map…, Diagnostics… buttons.</p>
</div>

<p>Configure the <b>SVD computation range</b> using the <b>Configure SVD range…</b>
button — this restricts which part of the spectrum is used for the SVD.
After changing the range, press <b>Update Map</b> to recompute. Switching
to a different Map Type and back to SVD does <i>not</i> require Update
Map, as long as the range (or anything else that affects the fit) hasn't
changed in between — the already-computed result simply reappears.</p>
<p><b>Component selector:</b> browse components instantly after computing;
no recomputation needed. The label mode (Explained var.%, σ, or Residual
error) controls the text shown next to each component.</p>
<p><b>Invert:</b> flips the sign of U[:,k] and V<sup>T</sup>[k,:] simultaneously.
SVD sign is arbitrary; use Invert when the map or subspectrum appears upside-down.</p>
<p><b>Multi-map… / Diagnostics…</b> open the multi-component grid view and the
SVD diagnostics window respectively.</p>

<h4>Multi-map… window</h4>
<p>Opens a separate window comparing several components side-by-side: each
selected component gets its own row with its 2-D map on the left and its
subspectrum U[:,k] on the right. Check/uncheck components in the scrollable
list on the left to add or remove rows; click a row to highlight it (blue),
then press <b>Invert</b> to flip that component's sign without leaving the
window. <b>Clear selection</b> unchecks everything at once. The first three
components are ticked by default when the window opens.</p>

<div class="screenshot">
    <img src="$MULTI_MAP_RESULT" width="$MULTI_MAP_RESULT_W" height="$MULTI_MAP_RESULT_H" alt="SVD Multi-Component Map window comparing three components side-by-side" />
    <p class="caption">SVD Multi-Component Map window: the first three components selected by default, each row showing its 2-D map (left) and subspectrum (right).</p>
</div>

<div class="note">
<b>Coefficient values are unit-normalized.</b> The V<sup>T</sup>[k,:] values
plotted here (and in this dialog's Export Map… CSV/Excel output) have unit
length — they are <i>not</i> multiplied by the singular value σ<sub>k</sub>.
This matches the standalone <b>PCA Scores &amp; Loadings</b> tool's own
"Scores" convention. If you need scikit-learn/Jolliffe-convention
(σ-scaled) PCA scores instead: this map has its own independent SVD/PCA,
computed over whatever spectra and range are active here, so its σ values
generally won't match the standalone tool's (which decomposes whatever it
currently has loaded) unless you go out of your way to match spectra and
range exactly. Export Map… avoids that trap — its note names this exact
component's own σ directly, so multiplying every exported value by that
number always gives the correct conversion for <i>this</i> map.
</div>

<div class="note">
All spectra must share the same x-axis for SVD — it combines every spectrum
into one matrix to find components shared across the whole batch, which only
means anything if they're all on the same wavenumber grid. If they aren't,
computing the map refuses with a message naming the mismatched spectrum,
rather than silently combining unrelated wavenumber positions. Use the Data
Range operation (with linearisation) to put them on a common axis first.
</div>

<h4>Spectrum panel in SVD mode</h4>
<p>In SVD mode, the spectrum panel's role shifts: instead of showing
configured bands (as in Intensity/Arithmetic/Cluster mode), it lets you
compare the clicked pixel's spectrum directly against the SVD component
that generated its map value — this is why <b>Show range bands</b> isn't
available here.</p>

<div class="screenshot">
    <img src="$SVD_SPECTRUM_PANEL" width="$SVD_SPECTRUM_PANEL_W" height="$SVD_SPECTRUM_PANEL_H" alt="Spectrum panel in SVD mode comparing the clicked spectrum against the SVD component" />
    <p class="caption">Clicked pixel's spectrum (blue, left axis) compared against the SVD component (orange dashed, right axis, "U amplitude"); the panel title states the clicked pixel's Row/Col (1-based). If "Show reconstructed spectrum using N components" is checked, the reconstruction appears as a green dashed line on the same (left) axis as the raw spectrum.</p>
</div>

<p>Three display options in the spectrum panel header:</p>
<ul>
  <li><b>Show SVD component</b> — overlays the SVD subspectrum (orange dashed) on a twin axis.</li>
  <li><b>Full spectrum</b> — when unchecked (default), the panel shows the spectrum
      clipped to the SVD range so the x-axis matches the component exactly.
      When checked, shows the full input spectrum with the SVD range shaded
      and the component on a twin axis.</li>
  <li><b>Show reconstructed spectrum using N components</b> — unchecked by
      default; overlays the spectrum rebuilt from the first N fitted
      components (green dashed). N has its own spinbox, right next to the
      checkbox — deliberately separate from the <b>Browse component</b>
      dropdown above, which just browses one component's own map/shape at
      a time. It
      defaults to using every fitted component (full reconstruction) until
      you dial it down, and its range always tracks however many components
      are actually fitted. Unlike a single component's own subspectrum, a
      reconstruction is in the same intensity units as the clicked-pixel
      spectrum, so it's drawn directly on the main axis rather than a twin
      axis — the more components included, the closer it should track the
      measured spectrum.</li>
</ul>

<div class="screenshot">
    <img src="$SVD_FULL_RANGE" width="$SVD_FULL_RANGE_W" height="$SVD_FULL_RANGE_H" alt="Full spectrum view with the SVD computation range shaded and excluded sub-range hatched" />
    <p class="caption">"Full spectrum" checked: the full input spectrum is shown, with the SVD computation range shaded (solid) and an excluded sub-range hatched.</p>
</div>
</div>

<h3>◉ PCA</h3>
<div class="cat">
<p>Computes Principal Component Analysis on the range-filtered spectra and
maps the resulting score vector as pixel values — the same underlying
computation as <b>SVD</b> above, with one difference: before
the decomposition, the per-wavelength average across every selected pixel
is subtracted first (mean-centering), the standard PCA convention. This
matches the standalone <b>PCA Scores &amp; Loadings</b> tool's own default,
and the standalone <b>Mean-Center Spectra (Dataset)</b> operation's
rationale — removing whatever level or shape every pixel's spectrum shares
in common so the decomposition finds only how they differ.</p>

<div class="screenshot">
    <img src="$TYPE_PCA" width="$TYPE_PCA_W" height="$TYPE_PCA_H" alt="Map Type panel with PCA selected" />
    <p class="caption">Map Type panel in PCA mode: Browse-component selector, Invert, Multi-map… buttons (Diagnostics… stays SVD-only).</p>
</div>

<p>The Map Type panel, Component selector, <b>Configure PCA range…</b>
button, and spectrum panel all work exactly like <b>SVD</b>
above — including <b>Invert</b> and <b>Multi-map…</b>, which apply to PCA
too (it has the same sign ambiguity SVD does). <b>Diagnostics…</b> stays
SVD-only for now.</p>

<div class="screenshot">
    <img src="$PCA_SPECTRUM_PANEL" width="$PCA_SPECTRUM_PANEL_W" height="$PCA_SPECTRUM_PANEL_H" alt="Spectrum panel in PCA mode comparing the clicked spectrum against the PCA component" />
    <p class="caption">Clicked pixel's spectrum (blue, left axis) compared against the PCA component (orange dashed, right axis) — same layout as SVD mode's spectrum panel, including the Row/Col title and the optional green reconstruction overlay.</p>
</div>

<div class="note">
Since PCA and SVD decompose the <i>same</i> spectra differently
(mean-centered vs. not), their components will generally differ —
sometimes substantially, if every pixel shares a strong common
background. Try both and compare if you're not sure which better
isolates the structure you're looking for.
</div>

<div class="note">
All spectra must share the same x-axis for PCA, for the same reason as
SVD (see above) — mean-centering and decomposing only mean anything if
every pixel's spectrum is on the same wavenumber grid.
</div>
</div>

<h3>◉ NMF / MCR-ALS</h3>
<div class="cat">
<p>Two further spatial decomposition modes, alongside SVD: <b>NMF</b> runs
Non-negative Matrix Factorization and <b>MCR-ALS</b> runs Multivariate
Curve Resolution — Alternating Least Squares, on the range-filtered spectra.
Both reuse this app's existing NMF Analysis / MCR-ALS tools internally, so
results match what those standalone tools would produce for the same
spectra and settings.</p>

<div class="warn" style="border-left-color:#c0392b; background:#FDEDEC;">
<strong style="color:#c0392b;">Baseline-correct the map's spectra first
&mdash; this isn't optional.</strong> Unlike SVD/PCA map (below), NMF and
MCR-ALS are very sensitive to an uncorrected shared background: with real
Raman/IR maps, it can account for &gt;99.9% of the data's total variance,
leaving almost nothing for the components to tell pixels apart with. The
symptom is noisy, spiky-looking component spectra and a map that barely
resembles real structure, even though the reported fit quality looks fine
&mdash; and it looks fine specifically because of how <b>Lack of fit</b> is
computed: it's a residual normalised by the data's own total squared
magnitude, and an uncorrected shared background dominates that total so
completely that even a trivial fit which barely distinguishes pixels from
each other can already report a lack-of-fit under 1%. In other words, a
suspiciously tiny lack-of-fit on NMF/MCR-ALS is itself a warning sign of
missing baseline correction, not confirmation of a good fit.
<strong>Apply Baseline correction (even an imperfect one) to your spectra
before switching to NMF or MCR-ALS map mode</strong> &mdash; see the
standalone NMF / MCR-ALS help pages' "Read this first" sections for why.
</div>

<div class="screenshot">
    <img src="$TYPE_NMF" width="$TYPE_NMF_W" height="$TYPE_NMF_H" alt="Map Type panel with NMF selected" />
    <p class="caption">Map Type panel in NMF mode: Components-to-fit spinner, Browse-component selector, and Configure NMF range&hellip; button.</p>
</div>

<div class="screenshot">
    <img src="$TYPE_MCR" width="$TYPE_MCR_W" height="$TYPE_MCR_H" alt="Map Type panel with MCR-ALS selected" />
    <p class="caption">Map Type panel in MCR-ALS mode: Components-to-fit spinner, Browse-component selector, and Configure MCR-ALS range&hellip; button.</p>
</div>

<p>Unlike SVD (which yields every component from a single fit), NMF and
MCR-ALS need the number of components chosen <i>before</i> fitting. A
<b>Components to fit</b> spinner (2–20, capped by the number of spectra in
the map) shares a row with the component selector in these two modes — set
it, then press <b>Update Map</b> to fit and show component 1. Changing it
requires pressing <b>Update Map</b> again; browsing already-fitted
components with the <b>Browse component</b> dropdown does not — and until
you do, changing <b>Components to fit</b> greys out the <b>Browse
component</b> dropdown and shows "Components changed — press 'Update Map'
to refit" in red, so the dropdown's item count and EV%s are never left
silently describing the old fit. (The two are deliberately worded
differently, rather than both just saying "Component[s]", since one sets
how many to fit and the other picks which already-fitted one to browse.)
Switching to a different Map Type and back to NMF or MCR-ALS does not
require Update Map either, as long as Components to fit — and the range,
and the reference spectra — haven't changed in between; the already-fitted
result simply reappears.</p>

<p>Configure the spectral range used for the fit with <b>Configure NMF
range…</b> / <b>Configure MCR-ALS range…</b> — the same restrict-to-region
mechanism as SVD's <b>Configure SVD range…</b>. The <b>Browse component</b>
dropdown's label is always <b>Explained var.(%)</b> in these two modes (σ
and Residual error, meaningful only for SVD, aren't offered).</p>

<p>Below the Components-to-fit spinner, each mode shows its own fit-control
settings — previously fixed at the standalone tools' defaults, now
adjustable here too:</p>
<ul>
  <li><b>NMF</b> — <b>Init.</b> (nndsvda / nndsvd) and <b>Max iter.</b>,
      same meaning as the standalone NMF Analysis tool's Initialisation and
      Max iterations fields.</li>
  <li><b>MCR-ALS</b> — <b>Max iter.</b>, plus the three constraint
      checkboxes from the standalone MCR-ALS tool: <b>Non-neg. C</b>
      (non-negative concentrations), <b>Non-neg. ST</b> (non-negative pure
      spectra), and <b>Closure</b> (concentrations sum to 100% per pixel —
      same caveat as the standalone tool: only turn this on if the system
      genuinely has closure).</li>
</ul>

<p><b>Run N times, keep best…</b> does the same job as <b>Update
Map</b> — both (re)compute the map from the current settings — but
instead of one deterministic fit, it re-fits several times with
different random starting points and keeps whichever run best
represents the near-best group, the same robustness check as the
standalone tools' button of the same name. Every run refits every
pixel in the map, so this can take noticeably longer than a single
<b>Update Map</b> press on a large map; there's a wait cursor but no
live progress or cancel button while it runs.</p>

<div class="note">
<b>Reference spectra (optional)</b> anchors a component slot to a known
component spectrum — the most effective way to remove NMF/MCR-ALS's
rotational ambiguity. Unlike the standalone tools' dropdown list (fine
for a handful of spectra, unusable for a map's hundreds or thousands of
pixels), a reference here is picked by clicking its pixel directly on
the map: press <b>Pick on map…</b> next to a component row — it turns
green and relabels itself <b>Click the map…</b> while armed, so it's
obvious which mode you're in — then click the pixel whose spectrum
should anchor that component (the same click-a-pixel gesture used
everywhere else in this dialog; pressing the button again cancels
without picking). While a row is armed this way, hovering the map also
shows a small preview of the spectrum under the cursor, to help judge
where to click before committing. Each picked pixel is marked on the
map with a numbered yellow circle matching its component number;
<b>View</b> re-opens that spectrum in its own plot at any time, and the
red <b>X</b> button clears the row. This also works a little
differently than in the standalone tools in one respect: there, a
picked reference can be excluded from the fitted data ("References are
external"); here it always stays part of the fit, because removing a
pixel would leave fewer spectra than Rows &times; Cols, breaking the
map's fixed grid. <b>Hold references fixed</b> still works the same
way — checked pins the component to the reference exactly; unchecked
uses it only as a starting guess.
</div>

<div class="note">
Picking, clearing, or fixing a reference after a map is already
displayed does <i>not</i> recompute it automatically — refitting
every pixel on every click would be disruptive on a large map. Instead
a small orange note appears (<i>"References changed — press 'Update
Map' to apply."</i>) while the map itself stays exactly as it was, so
nothing is hidden while you decide when to recompute. Check
<b>Auto-recompute when references change</b> to switch to the
opposite behaviour instead — every such change recomputes right away,
no reminder needed, at the cost of a full refit on every pick, clear,
or fixed-reference toggle.
</div>

<div class="screenshot">
    <img src="$REF_SPECTRA_PANEL" width="$REF_SPECTRA_PANEL_W" height="$REF_SPECTRA_PANEL_H" alt="Reference spectra groupbox showing an armed pick button, numbered markers, and the View/X buttons" />
    <p class="caption">Reference spectra groupbox: one row armed for picking (green <b>Click the map…</b>), one already picked with its <b>View</b> and red <b>X</b> buttons enabled, and the corresponding numbered markers on the map.</p>
</div>

<p>After a fit, a status line below these controls reports <b>Lack of
fit</b> and the iteration count (and, after "Run N times, keep best…",
the consensus among the near-best runs) — the same fit-quality figures
the standalone tools show next to their Run button. On real, noisy maps
this number typically plateaus well above 0% — often in the 15&ndash;25%
range — once the first few components have captured the actual chemistry,
since it also counts point-to-point measurement noise that no component
model can fit; see the standalone NMF / MCR-ALS help pages' "Lack of fit"
notes for the full explanation.</p>

<div class="note">
NMF and MCR-ALS components are constrained non-negative (MCR-ALS enforces
this by default on both the concentration profiles and the pure spectra;
NMF is non-negative by construction), so a sign flip would produce a result
the algorithm itself forbids. For this reason <b>Invert</b> and <b>Multi-map…</b> — available for SVD
and PCA, both of which do have this ambiguity — plus <b>Diagnostics…</b>
(SVD-only) are hidden in these two modes.
</div>

<div class="note">
As with SVD, all spectra must share the same x-axis — the fit combines
every spectrum into one problem, which only means anything if they're all
on the same wavenumber grid. A mismatch refuses with a message naming the
mismatched spectrum. Use the Data Range operation (with linearisation) to
put them on a common axis first.
</div>

<p>The spectrum panel works exactly as in SVD mode: click a pixel to compare
its spectrum against the fitted component, and <b>Full spectrum</b> toggles
between the clipped fit-range view and the full input spectrum with the fit
range shaded. The overlay checkbox relabels itself to name whichever kind is
active — <b>Show NMF component</b> or <b>Show MCR-ALS component</b> — but
otherwise behaves identically to <b>Show SVD component</b> above.
<b>Show reconstructed spectrum using N components</b> works the same way
here too, reconstructing from whichever fit — NMF or MCR-ALS — is active.
Its N spinbox is independent of both the <b>Browse component</b> dropdown
and the <b>Components to fit</b> spinner in the Map Type panel above (which
sets how many components to <i>fit</i>, and only takes effect after
pressing <b>Update Map</b>) — it works on whatever is already fitted right
now.</p>

<div class="screenshot">
    <img src="$NMF_MCR_SPECTRUM_PANEL" width="$NMF_MCR_SPECTRUM_PANEL_W" height="$NMF_MCR_SPECTRUM_PANEL_H" alt="Spectrum panel in NMF/MCR-ALS mode comparing the clicked spectrum against the component" />
    <p class="caption">Clicked pixel's spectrum (blue, left axis) compared against the NMF or MCR-ALS component (orange dashed, right axis) — same as SVD mode, including the Row/Col title and the optional green reconstruction overlay.</p>
</div>
</div>

<h3>◉ Cluster overlay</h3>
<div class="cat">
<p>Runs k-means clustering directly on the map spectra and colours each pixel
by its cluster assignment. No external Cluster Analysis step is required.</p>

<div class="screenshot">
    <img src="$TYPE_CLUSTER" width="$TYPE_CLUSTER_W" height="$TYPE_CLUSTER_H" alt="Map Type panel with Cluster overlay selected" />
    <p class="caption">Map Type panel in Cluster overlay mode: Method, k (clusters), and clustering range controls.</p>
</div>

<table>
<tr><th>Setting</th><th>Description</th></tr>
<tr><td><b>Method</b></td><td><b>K-means:</b> standard algorithm, accurate, suitable for up to ~5 000 spectra.<br>
<b>MiniBatch K-means:</b> faster approximation for very large maps.</td></tr>
<tr><td><b>k (clusters)</b></td><td>Number of clusters (2–20). Start small (3–5) and increase if spatial variation is not captured.</td></tr>
<tr><td><b>Clustering range</b></td><td>Configure which spectral region is used for clustering via <b>Configure clustering range…</b>. Restricting to a fingerprint region improves chemical discrimination.</td></tr>
</table>
<p>After computing, the <b>Show cluster averages…</b> button opens a dialog
showing the mean spectrum of each cluster (colour-matched to the map)
and offering export of cluster averages to the main spectrum list.</p>

<div class="note">
All spectra must share the same x-axis for clustering — like SVD, it compares
every spectrum against every other one at each wavenumber, which only means
anything if they're all on the same grid. A mismatch refuses with a message
rather than silently comparing unrelated positions.
</div>

<div class="screenshot">
    <img src="$CLUSTER_MAP_RESULT" width="$CLUSTER_MAP_RESULT_W" height="$CLUSTER_MAP_RESULT_H" alt="2D map coloured by k-means cluster assignment" />
    <p class="caption">The map after clustering: each pixel coloured by its cluster assignment (fixed discrete tab10 palette).</p>
</div>

<div class="note">
Each mode (Intensity, Arithmetic Band A, Arithmetic Band B, SVD, Cluster) has
its own <b>independent spectral range configuration</b>. Changing the range for
one mode does not affect any other mode.
</div>
</div>

<h3>◉ RGB overlay</h3>
<div class="cat">
<p>Combines up to three already-computed component maps into a single
false-color composite — assign one component to each of the Red, Green
and Blue channels. This is a standard technique in hyperspectral/Raman
mapping software for showing where several chemical components co-occur
in one picture, instead of flipping between separate single-component
maps.</p>

<div class="note">
<b>Grayed out until a decomposition is computed.</b> The <b>RGB overlay</b>
radio button stays disabled until at least one SVD, PCA, NMF or MCR-ALS
map has been computed for the current dimensions — there is nothing yet
to combine. Compute any one of them first (any kind, any number of
components), and the radio becomes selectable immediately, without
needing to switch away and back.
</div>

<p>Selecting <b>RGB overlay</b> shows its own panel in the right-hand
column, exactly like SVD or Cluster overlay get their own panel — three
boxes labelled <b>Red</b>, <b>Green</b> and <b>Blue</b>, each with an
<b>Enable</b> checkbox, a <b>Source</b> dropdown (SVD / PCA / NMF /
MCR-ALS) and a <b>Component</b> dropdown. All three channels start
disabled; enable the ones you want. A kind that hasn't actually been
computed yet simply leaves its Component dropdown empty for that
channel. Sources can be mixed freely — for example an NMF component in
Red and an MCR-ALS component in Green — since each channel just reads
whichever cache already has data, nothing is computed on the fly.</p>

<div class="screenshot">
    <img src="$TYPE_RGB" width="$TYPE_RGB_W" height="$TYPE_RGB_H" alt="Map Type panel with RGB overlay selected" />
    <p class="caption">Map Type panel in RGB overlay mode: Red/Green/Blue channel boxes, each with its own Enable checkbox, Source and Component dropdowns.</p>
</div>

<p>Unlike SVD/PCA/NMF/MCR-ALS, <b>RGB overlay</b> never requires an
explicit <b>Update Map</b> press, at any point — composing a composite
from components that are already sitting in the decomposition cache is
cheap, unlike a fresh fit. Switching to <b>RGB overlay</b> with at least
one channel already enabled and configured (for example, switching back
from another mode) displays the composite immediately. Checking a
channel's <b>Enable</b> box for the very first time, changing its
<b>Source</b> or <b>Component</b>, or changing the percentile stretch
below all redraw the map live and immediately as well. The <b>Update
Map</b> button is still there and works, but pressing it is never
required in this mode.</p>

<p>There is a single, shared <b>Low %</b> / <b>High %</b> setting
(0% / 100% by default, meaning the plain min–max), not one per channel
— but it is applied to each enabled channel's <i>own</i> values
independently, so the actual cutoff numbers it produces are normally
different for each channel. For example, if Red is an SVD component
ranging roughly -0.3 to +0.5 and Green is an NMF component ranging 0 to
12, the same "0% / 100%" setting means "use SVD's own min/max" for Red
and "use NMF's own min/max" for Green — two different absolute cutoffs
from one shared percentage.</p>

<div class="note">
<b>This stretch never changes your actual decomposition results.</b> It
exists purely to squeeze each channel's real values into the 0–1 range
the picture needs, and is recomputed fresh every time the map redraws —
it is not saved anywhere. Switch to that component's own single-component
map view, or export it to CSV, and you'll see the original, untouched
values. This is different from the single-component map view's
<b>Invert</b> button, which <i>does</i> permanently flip that component's
sign in the underlying SVD/PCA data until inverted again — the contrast
stretch here has no equivalent persistent effect.</div>

<p>A disabled channel simply contributes nothing (pure black) to that
channel — a red/green-only, or even single-channel, overlay is a normal
result, not an error.</p>

<p>Because ROI selection and pixel-click spectrum inspection work "as in
other modes" here too, clicking a pixel shows its actual
<b>R=.. G=.. B=..</b> values (display-scaled 0–1) instead of a generic
scalar map value, and drawn ROIs still let you inspect or overlay the
spectra inside them. The map's own toolbar also shows the same three
values continuously as <code>[R, G, B]</code> in its top-right corner
while the mouse moves, with no click needed — see "Coordinate &amp;
value readout" further below in the Spectrum Panel section. Two
things are disabled in this mode specifically,
because they assume a single scalar per pixel: <b>ROI comparison
statistics</b> (there's no single number to compare across regions) and
<b>Export map (CSV/Excel)…</b> — use the panel's own <b>Export as
PNG…</b> button instead, which saves the composite at native resolution
(one image pixel per map pixel), independent of whatever on-screen
<b>Equal aspect ratio</b> or <b>Interpolation</b> display option happens
to be active.</p>

<div class="screenshot">
    <img src="$RGB_OVERLAY_RESULT" width="$RGB_OVERLAY_RESULT_W" height="$RGB_OVERLAY_RESULT_H" alt="RGB overlay composite map with a clicked pixel showing R/G/B values" />
    <p class="caption">A finished RGB overlay composite. The status line below the map shows the clicked pixel's actual R=.. G=.. B=.. values, not a generic map value.</p>
</div>
</div>

<hr>
<h2>3 — Spectral Range Configuration</h2>

<div class="cat">
<p>Each mode has its own independent spectral range, configured via a button
in the band panel: <b>Configure Band…</b> in Intensity mode, <b>Configure SVD
range…</b> in SVD mode, <b>Configure clustering range…</b> in Cluster mode.
In Map arithmetic, two separate buttons appear — <b>Configure Band A…</b> and
<b>Configure Band B…</b> — letting you define both bands used in the A/B
operation independently. All of these buttons open the same dedicated range
dialog:</p>

<div class="screenshot">
    <img src="$CONFIGURE_RANGE" width="$CONFIGURE_RANGE_W" height="$CONFIGURE_RANGE_H" alt="Configure range dialog with Include/Exclude toggle, range list, and preview plot" />
    <p class="caption">The range configuration dialog: Include/Exclude toggle, range list, and draggable preview plot.</p>
</div>

<ul>
  <li><b>Include / Exclude mode toggle</b> — include: only the listed ranges
      are used; exclude: the listed ranges are removed and the rest is used.</li>
  <li><b>Range list</b> — add ranges with the From/To spinboxes or by
      <b>clicking and dragging directly on the preview plot</b>.</li>
  <li><b>Preview plot</b> — shows N evenly-spaced spectra from the map
      (adjust N with the spinbox) plus the <b>average of all spectra</b>
      (black bold line, toggled with "Show average spectrum" checkbox).
      Configured ranges are shaded in the band's colour.</li>
  <li>Include ranges: solid shade. Exclude ranges: hatched pattern.</li>
</ul>
<div class="tip">
<b>Tip:</b> Drag on the preview plot to define a range visually — it is
added to the list immediately.
</div>
</div>

<hr>
<h2>4 — Display Options</h2>

<div class="cat">
<div class="screenshot">
    <img src="$DISPLAY_OPTIONS" width="$DISPLAY_OPTIONS_W" height="$DISPLAY_OPTIONS_H" alt="Display Options group: Colormap, Interpolation, Equal aspect ratio, Auto colorbar range" />
    <p class="caption">The Display Options group.</p>
</div>

<table>
<tr><th>Option</th><th>Description</th></tr>
<tr><td><b>Colormap</b></td><td>Matplotlib colormap. Perceptually uniform colormaps (viridis, plasma) are recommended; diverging colormaps (coolwarm, RdBu_r) are useful for SVD coefficients or difference maps.</td></tr>
<tr><td><b>Interpolation</b></td><td><i>nearest</i> shows discrete pixels (recommended for small maps); <i>bilinear</i>/<i>bicubic</i> apply smoothing.</td></tr>
<tr><td><b>Equal aspect ratio</b></td><td>Displays each pixel as a square, preserving physical shape. Uncheck when rows and columns differ greatly.</td></tr>
<tr><td><b>Auto colorbar range</b></td><td>When unchecked, set <b>Low %</b> and <b>High %</b> percentile clipping. For example, Low=2 / High=98 clips the bottom and top 2% of map values — useful to suppress outlier pixels without losing information in the bulk of the map.</td></tr>
</table>
<p>Colormap and interpolation are not applicable to Cluster overlay (which uses a fixed discrete tab10 palette).</p>
</div>

<hr>
<h2>5 — Spectrum Panel (lower right)</h2>

<div class="cat">
<p>The lower-right panel shows the spectrum for the clicked pixel.
The full input spectrum is always shown (the range configuration only
affects which region is used for <i>computing</i> the map value, not the display).
Its title always states the clicked pixel's <b>Row</b>/<b>Col</b> explicitly
(1-based — the map's first row/column is Row 1, Col 1), in every mode —
not just when the spectrum's own label happens to encode it (true only for
WITec MAT imports' <code>[rNN_cNN]</code>-style labels; other import
formats have no such label to read a position off of).</p>

<div class="screenshot">
    <img src="$SPECTRUM_PANEL" width="$SPECTRUM_PANEL_W" height="$SPECTRUM_PANEL_H" alt="Spectrum panel showing the spectrum for the clicked pixel" />
    <p class="caption">The spectrum panel, showing the spectrum at the clicked pixel, with its Row/Col (1-based) stated in the title.</p>
</div>

<h3>Show range bands checkbox</h3>
<p>Overlays shaded regions on the spectrum showing the configured band(s).
In Arithmetic mode: Band A in blue, Band B in red. Overlapping bands show
as a blended colour. Available in Intensity, Arithmetic, and Cluster modes.</p>

<h3>Hover tooltip</h3>
<p>Move the mouse over any map pixel without clicking to see a tooltip
showing the pixel's Row/Col (1-based, same convention as everywhere else
in this dialog), its spectrum label, and the map value at that position.</p>

<div class="screenshot">
    <img src="$HOVER_TOOLTIP" width="$HOVER_TOOLTIP_W" height="$HOVER_TOOLTIP_H" alt="Hover tooltip showing spectrum label and map value at the cursor position" />
    <p class="caption">Hovering over a pixel shows its Row/Col (1-based), spectrum label, and map value.</p>
</div>

<h3>Coordinate &amp; value readout (top-right, above the map)</h3>
<p>Independently of the hover tooltip above, the map's own navigation
toolbar shows a small live readout in its top-right corner while the
mouse is over the plot: <code>(x, y) = &hellip;</code> gives the cursor's
data coordinates, and the bracketed number(s) beneath it give the
underlying image array's raw value at that exact pixel. For every
scalar map type (Intensity, SVD, PCA, NMF, MCR-ALS, Cluster overlay, Map
arithmetic) that's a single number; in <b>RGB overlay</b> mode it shows
three numbers, <code>[R, G, B]</code> — the same display-scaled 0&ndash;1
values the composite image is drawn from, in the same order as the
<b>R=.. G=.. B=..</b> readout in the click-info status line beneath the
map. This toolbar readout updates continuously as the mouse moves, with
no click and no hover-dwell needed — matplotlib provides it automatically
for any image and it is always available, independent of both the hover
tooltip and the click-info line.</p>
</div>

<hr>
<h2>6 — ROI Tools</h2>

<div class="cat">
<p>All ROI tools are accessible via the <b>ROI ▾</b> dropdown menu.
Only one tool can be active at a time — activating any tool automatically
deactivates the others.</p>

<div class="note">
<b>ROI regions persist across Map Type switches.</b> Drawing a region
while looking at, say, SVD and then switching to NMF, Intensity metric,
or RGB overlay keeps every region exactly as drawn — the outlines
redraw on whichever map is now showing, and <b>View/Remove ROI
regions…</b> still lists them all. The one thing that <i>does</i> clear
every region is actually changing <b>Rows × Cols</b> in the Map
Dimensions group: a region's shape is stored as row/col grid positions,
so reshaping the grid (even to a different still-valid factor pair) can
leave those positions pointing at the wrong pixels, and there's no way
to know they're still meaningful — switching Map Type never changes the
grid shape, only what's computed from it, so regions stay valid there.
</div>

<div class="screenshot">
    <img src="$ROI_MENU" width="$ROI_MENU_W" height="$ROI_MENU_H" alt="ROI dropdown menu expanded, showing all ROI tool entries" />
    <p class="caption">The ROI ▾ dropdown menu, expanded.</p>
</div>

<table>
<tr><th>Tool</th><th>How to use</th></tr>
<tr><td><b>Add ROI rectangle…</b></td><td>Click and drag to draw a rectangle. The selector stays active — draw multiple rectangles in one session. Becomes "Cancel ROI rectangle" while active.</td></tr>
<tr><td><b>Add ROI ellipse…</b></td><td>Click and drag to draw an ellipse. Pixels inside the ellipse (exact point-in-ellipse test) are selected. Useful for circular or elliptical features.</td></tr>
<tr><td><b>Paint ROI lasso…</b></td><td>Freehand drawing — click and drag any shape. All pixels inside the closed path are selected.</td></tr>
<tr><td><b>Add ROI line profile…</b></td><td>Two-click line: first click sets the start, second click sets the end. Pixels along the Bresenham line are selected. The ROI spectra viewer in Line profile mode shows a spatial profile plot. Draw several lines in one session — they're numbered Line 1, Line 2, … in the order drawn (see below).</td></tr>
</table>

<div class="screenshot">
    <img src="$ROI_RECTANGLE" width="$ROI_RECTANGLE_W" height="$ROI_RECTANGLE_H" alt="Map with an ROI rectangle drawn" />
    <p class="caption">An ROI rectangle drawn on the map, with the Include/Exclude mode indicator.</p>
</div>

<div class="note">
<b>Shaded box vs. dashed outline while drawing (rectangle/ellipse):</b>
while you're actively dragging out a rectangle or ellipse, you'll see a
translucent, colour-filled shape with small square/circle handles — that's
the drawing tool itself, still adjustable. The moment you release the
mouse, that shape is recorded as a region and shown from then on as a
plain white dashed outline (no fill) — that's the permanent marker for a
region you've kept. The shaded tool disappears as soon as the region is
committed and only reappears once you start dragging the next one, so at
rest you'll only ever see the dashed outlines of your saved regions.</div>

<h3>Include / Exclude mode</h3>
<p><b>Mode: Include ◯</b> — spectra inside drawn regions are selected.<br>
<b>Mode: Exclude ●</b> — spectra inside drawn regions are <i>excluded</i>;
everything outside is selected.</p>
<p>The <b>View ROI spectra</b> action always shows the effective count:
in include mode a single number (e.g. <i>414</i>);
in exclude mode both counts (e.g. <i>4261 | excl. 414</i>).</p>

<h3>View / Remove ROI regions…</h3>
<p>Opens a dialog listing all drawn regions (rectangles, ellipses, lassos,
lines), in the order they were drawn. Click a row to highlight that region
in yellow on the map — useful just to identify which region is which,
without removing anything. Select one or more (Ctrl/Shift for multi-select)
and press <b>Remove selected</b> to delete them, or <b>Cancel</b> to close
without changes.</p>
<p>Line-type rows also show which line number that region corresponds to in
the ROI spectra viewer's Line profile mode — e.g. <i>Region 4: line
(39,70)→(19,67) (21 spectra) (Line 3)</i> — since a line's number only
counts other lines (skipping rectangles/ellipses/lassos drawn in between),
so it can differ from its plain Region number.</p>

<h3>ROI comparison statistics…</h3>
<p>Available when two or more regions exist and a map has been computed.
Shows a table of <b>mean ± std, min, median, max</b> of the map value within
each region. The metric label adapts to the current map mode. Export to CSV
is available.</p>

<div class="screenshot">
    <img src="$ROI_COMPARISON" width="$ROI_COMPARISON_W" height="$ROI_COMPARISON_H" alt="ROI comparison statistics table" />
    <p class="caption">The ROI comparison statistics table.</p>
</div>

<h3>View ROI spectra…</h3>
<p>Opens the ROI viewer showing all spectra in the current selection.
Options include:</p>

<div class="screenshot">
    <img src="$ROI_VIEWER" width="$ROI_VIEWER_W" height="$ROI_VIEWER_H" alt="ROI spectra viewer window" />
    <p class="caption">The ROI spectra viewer, with its view-mode dropdown and Average ± N·σ display options.</p>
</div>

<ul>
  <li><b>Overlay</b> — all selected spectra on one axes, with a legend.</li>
  <li><b>Grid</b> — individual spectra in a grid.</li>
  <li><b>Waterfall</b> — spectra stacked with a vertical offset (auto or manual), with a legend.</li>
  <li><b>Heatmap</b> — spectra as image rows (colour = intensity); handy for scanning many spectra
      at once for consistency or outliers.</li>
  <li><b>Difference</b> — every selected spectrum minus a chosen reference spectrum, with a legend.
      If the reference spectrum gets unselected, the viewer automatically picks a new one and flags
      this once in the plot title so you don't mistake it for your original choice.</li>
  <li><b>Line profile</b> — for line ROIs: map value vs. position along the line. With two or more
      lines drawn, each is numbered and colour-coded separately (Line 1, Line 2, …) so they aren't
      merged into one meaningless sequence.</li>
  <li><b>Average ± N·σ</b> — mean spectrum with shaded standard deviation band (Overlay/Grid modes).</li>
  <li><b>Display limit</b> — in Grid/Waterfall this caps how many spectra are actually plotted
      (too many subplots or stacked traces become unreadable); in Overlay/Difference it only caps
      the legend, since those modes handle any number of spectra fine — just the legend gets
      unreadable past a point. Not used in Heatmap. Click the small <b>?</b> button next to it for
      a reminder of which applies where. It's adjustable in the dialog itself, so raise it if you
      need to see more at once.</li>
  <li><b>Send to main list…</b> — adds selected spectra (individually or as their average)
      to the main spectrum list for further processing. The list is re-sorted afterward
      (matching the main window's current sort order) and the newly added spectra are
      selected, so they're immediately visible and ready to work with.</li>
  <li><b>Export selected…</b> — saves to CSV or Excel.</li>
</ul>

<div class="note">
<b>Selecting spectra in this list</b> works the same way as the main spectrum
list — click to select one, Ctrl/Shift-click to select several, or use
<b>Select All</b> / <b>Unselect All</b>. There are no checkboxes.</div>

<div class="note">
<b>Average ± N·σ</b>, sending an <b>average</b> to the main list, and
<b>Export selected…</b> all combine multiple spectra together, so all of them
require a shared x-axis the same way SVD and Cluster do. A mismatch refuses
with a message naming which spectrum doesn't match, rather than silently
combining or exporting mislabeled data. Overlay, Grid, Line profile, and
sending spectra individually (not as an average) don't combine anything, so
they work regardless of whether spectra share an axis.
</div>
</div>

<hr>
<h2>Typical workflows</h2>

<div class="cat">
<h3>Quick band-intensity map</h3>
<ol>
  <li>Select all mapping spectra in the main window.</li>
  <li>Open 2D Map; enter or suggest correct dimensions.</li>
  <li>Click <b>Configure Band…</b> and drag a range over your band of interest.</li>
  <li>Leave metric = <i>Integral</i> — map draws automatically.</li>
  <li>Click pixels to inspect spectra; use ROI tools to compare regions.</li>
</ol>
</div>

<div class="cat">
<h3>Band-ratio map (two bands)</h3>
<ol>
  <li>Switch to <b>Map arithmetic</b>.</li>
  <li>Click <b>Configure Band A…</b> and define the numerator band.</li>
  <li>Click <b>Configure Band B…</b> and define the denominator band.</li>
  <li>Set Operation to <b>A / B</b>.</li>
  <li>Map redraws automatically. Use a diverging colormap if values span 1.</li>
</ol>
</div>

<div class="cat">
<h3>SVD component map</h3>
<ol>
  <li>Apply baseline correction and normalisation beforehand if desired.</li>
  <li>Switch to <b>SVD</b> and optionally configure a SVD range.</li>
  <li>Press <b>Update Map</b>.</li>
  <li>Browse components in the dropdown to find chemically meaningful ones.</li>
  <li>Use <b>Invert</b> if the map appears upside-down.</li>
  <li>Use <b>Diagnostics…</b> to inspect singular values and find the noise floor.</li>
  <li>Use <b>Multi-map…</b> to compare several components side-by-side.</li>
</ol>
</div>

<div class="cat">
<h3>NMF / MCR-ALS component map</h3>
<ol>
  <li>Apply baseline correction and normalisation beforehand if desired.</li>
  <li>Switch to <b>NMF</b> or <b>MCR-ALS</b>.</li>
  <li>Set <b>Components to fit</b> to how many you expect (start with 2–4).</li>
  <li>Optionally configure the fit range via <b>Configure NMF/MCR-ALS range…</b>.</li>
  <li>Press <b>Update Map</b> to fit and show component 1.</li>
  <li>Browse components in the dropdown to find chemically meaningful ones.</li>
  <li>If a component looks noisy or redundant, refit with a different
      <b>Components to fit</b> count rather than looking for an Invert-style
      fix — NMF/MCR-ALS components are non-negative by construction.</li>
</ol>
</div>

<div class="cat">
<h3>Cluster map</h3>
<ol>
  <li>Switch to <b>Cluster overlay</b>.</li>
  <li>Optionally configure a clustering range (fingerprint region works well).</li>
  <li>Set k and method; press <b>Update Map</b>.</li>
  <li>Click <b>Show cluster averages…</b> to inspect mean spectra per cluster.</li>
  <li>Export cluster averages to the main list for further analysis (peak fitting, etc.).</li>
</ol>
</div>

</body></html>
""")

    return help_template.safe_substitute(images)
