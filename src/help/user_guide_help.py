# src/help/user_guide_help.py

"""
Help content for the general SpecAnalytiXBase User Guide.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "user_guide")

_SCREENSHOT_FILES = {
    "OVERVIEW":                    "main_window_overview.png",
    "IMPORT_DIALOG":               "import_spectra_dialog.png",
    "SPECTRUM_LIST_CONTEXT_MENU":  "spectrum_list_context_menu.png",
    "SPECTRUM_LIST":               "spectrum_list_panel.png",
    "RENAME_DIALOG":               "rename_spectra_dialog.png",
    "METADATA_DIALOG":             "spectrum_metadata_dialog.png",
    "METADATA_TABLE_DIALOG":       "spectrum_metadata_table_dialog.png",
    "SELECTION_DIALOG":            "spectra_selection_dialog.png",
    "PLOT_OVERLAY":                "plot_type_overlay.png",
    "PLOT_GRID":                   "plot_type_grid.png",
    "PLOT_WATERFALL":              "plot_type_waterfall.png",
    "PLOT_MEAN_SD":                "plot_type_mean_sd.png",
    "PLOT_DIFFERENCE":             "plot_type_difference.png",
    "PLOT_HEATMAP":                "plot_type_heatmap.png",
    "BAND_MARKERS":                "band_marker_manager.png",
    "PLOT_CONTEXT_MENU":           "plot_context_menu.png",
    "LEGEND_DIALOG":               "legend_properties_dialog.png",
    "PIPELINE_PANEL":              "spectra_processing_panel.png",
    "HISTORY_DIALOG":              "operations_history_dialog.png",
    "SAVE_DIALOG":                 "save_options_dialog.png",
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


def get_user_guide_help_title():
    return "SpecAnalytiXBase User Guide"


def get_user_guide_help_content():
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders), not str.format()/f-strings — the
    # CSS block below is full of literal { } braces that would collide with
    # .format()-style placeholders.
    help_template = Template("""
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1976D2; margin-top: 28px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            h3    { color: #F57C00; margin-top: 18px; }
            h4    { color: #555; margin-top: 14px; }
            a     { color: #1976D2; }
            .tip      { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .warning  { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .danger   { background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .info     { background-color: #e3f2fd; padding: 10px; margin: 8px 0; border-left: 4px solid #2196f3; border-radius: 0 5px 5px 0; }
            .pipeline { background-color: #fff3e0; padding: 12px; margin: 8px 0; border-left: 4px solid #ff9800; border-radius: 0 5px 5px 0; }
            .scheme   { background-color: #F4F5F7; border: 1px solid #D0D3DA; border-radius: 6px;
                        padding: 16px; margin: 12px 0; font-family: 'Courier New', monospace;
                        font-size: 10pt; line-height: 2.0; }
            .box      { background-color: #FFFFFF; border: 1px solid #B0B8C8; border-radius: 4px;
                        padding: 2px 10px; display: inline-block; }
            table { width: 100%; border-collapse: collapse; margin: 10px 0; }
            th    { background-color: #E3EAF4; color: #1976D2; padding: 7px 10px; text-align: left; }
            td    { padding: 6px 10px; border-bottom: 1px solid #E0E0E0; }
            tr:nth-child(even) { background-color: #F8F9FB; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
            .kbd { background-color: #f0f0f0; padding: 2px 6px; border-radius: 3px;
                   font-family: monospace; border: 1px solid #ccc; font-size: 9pt; }
            .ref { font-size: 8.5pt; color: #1976D2; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>

        <h1>SpecAnalytiXBase User Guide</h1>

        <!-- ═══════════════════════════════════════════════════════════
             QUICK START / OVERVIEW
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="overview">Overview &amp; Quick Start</h2>

        <p>SpecAnalytiXBase is a desktop application for importing, visualising, and
        processing spectroscopic data (Raman, IR, UV-Vis, NMR, fluorescence, and other
        techniques). It follows a clear <strong>pipeline model</strong>: each operation
        is selected, configured, and then applied to the chosen spectra in sequence.</p>

        <div class="tip">
            <strong>New user? Start here in five steps:</strong>
            <ol>
                <li><strong>Import</strong> &mdash; File → Import data → new</li>
                <li><strong>Select</strong> spectra in the left-hand list</li>
                <li><strong>Choose</strong> an operation from the Spectra Processing dropdown</li>
                <li><strong>Run</strong> &mdash; click Run to open the operation's settings dialog</li>
                <li><strong>Commit</strong> &mdash; every operation's dialog has its own
                    <strong>Apply</strong> / <strong>Add as New</strong> buttons right inside it</li>
            </ol>
        </div>

        <h3 id="pipeline-scheme">Processing Pipeline — Schematic</h3>

        <table style="width:auto; border:none; border-collapse:separate; border-spacing:0;">
          <tr>
            <td style="background:#3A6AAF; color:white; font-weight:bold; font-size:10pt;
                        padding:8px 18px; border-radius:6px; text-align:center; border:none;">
              Spectra Processing
            </td>
          </tr>
          <tr><td style="border:none; text-align:center; padding:4px; color:#3A6AAF;">▼</td></tr>
          <tr>
            <td style="border:none;">
              <table style="width:100%; border:none; border-collapse:separate; border-spacing:6px;">
                <tr>
                  <td style="background:#E3EAF4; border:1px solid #B0B8C8; border-radius:5px;
                              padding:6px 12px; text-align:center; font-weight:bold; width:40%;">
                    1. Select operation
                  </td>
                  <td style="border:none; color:#3A6AAF; font-weight:bold; text-align:center; width:10%;">→</td>
                  <td style="background:#F4F5F7; border:1px dashed #B0B8C8; border-radius:5px;
                              padding:6px 12px; font-size:8.5pt; width:50%;">
                    Data range / Normalization /<br>
                    Smoothing / Baseline / SVD /<br>
                    Subtraction / Calculator / …
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr><td style="border:none; text-align:center; padding:4px; color:#3A6AAF;">▼</td></tr>
          <tr>
            <td style="border:none;">
              <table style="width:100%; border:none; border-collapse:separate; border-spacing:6px;">
                <tr>
                  <td style="background:#E3EAF4; border:1px solid #B0B8C8; border-radius:5px;
                              padding:6px 12px; text-align:center; font-weight:bold; width:40%;">
                    2. Run
                  </td>
                  <td style="border:none; color:#3A6AAF; font-weight:bold; text-align:center; width:10%;">→</td>
                  <td style="background:#F4F5F7; border:1px dashed #B0B8C8; border-radius:5px;
                              padding:6px 12px; font-size:8.5pt; width:50%;">
                    Opens settings dialog for the operation.<br>
                    Settings are remembered between sessions.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr><td style="border:none; text-align:center; padding:4px; color:#3A6AAF;">▼</td></tr>
          <tr>
            <td style="border:none;">
              <table style="width:100%; border:none; border-collapse:separate; border-spacing:6px;">
                <tr>
                  <td style="background:#2E7D32; color:white; border-radius:5px;
                              padding:6px 12px; text-align:center; font-weight:bold; width:40%;">
                    3. Apply
                  </td>
                  <td style="border:none; color:#3A6AAF; font-weight:bold; text-align:center; width:10%;">→</td>
                  <td style="background:#F4F5F7; border:1px dashed #B0B8C8; border-radius:5px;
                              padding:6px 12px; font-size:8.5pt; width:50%;">
                    Commits the operation to selected spectra.<br>
                    Uses last settings if Run was opened and closed without committing.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr><td style="border:none; text-align:center; padding:4px; color:#3A6AAF;">▼</td></tr>
          <tr>
            <td style="border:none;">
              <table style="width:100%; border:none; border-collapse:separate; border-spacing:6px;">
                <tr>
                  <td style="background:#E3EAF4; border:1px solid #B0B8C8; border-radius:5px;
                              padding:6px 12px; text-align:center; font-weight:bold; width:40%;">
                    4. History
                  </td>
                  <td style="border:none; color:#3A6AAF; font-weight:bold; text-align:center; width:10%;">→</td>
                  <td style="background:#F4F5F7; border:1px dashed #B0B8C8; border-radius:5px;
                              padding:6px 12px; font-size:8.5pt; width:50%;">
                    Review all applied operations in order,<br>
                    with full parameter details.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>

        <div class="tip">
            <strong>Steps 2 and 3 happen in the same dialog:</strong> Run opens the
            settings dialog for whichever operation you chose, and that dialog has its own
            <strong>Apply</strong> and <strong>Add as New</strong> buttons that commit
            immediately — Apply replaces the selected spectra; Add as New keeps the
            originals and adds the result under a new name. This is true for every
            operation in the Spectra Processing dropdown; there's no separate main-window
            commit step. See <a href="#pipeline">→ Processing Pipeline details</a> for more.
        </div>

        <div class="tip">
            <strong>Large batches:</strong> applying an operation to a large number of
            spectra shows a brief progress dialog ("Applying... → Updating spectrum
            list... → Redrawing plot...") so it's clear the app is still working, not
            frozen. It only appears above a few hundred spectra — a small selection
            commits without any dialog, exactly as before.
        </div>

        <p>Operations are applied incrementally and the full history is accessible
        via the <strong>History</strong> button. Use <a href="#pipeline">→ Processing
        Pipeline details</a> for a complete description of each step.</p>

        <div class="screenshot">
            <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="SpecAnalytiXBase main window overview" />
            <p class="caption">The main window: menu bar, spectrum list on the left, plot canvas in the centre, and the plot-option / processing panels along the bottom.</p>
        </div>

        <h3>Main Window Areas</h3>
        <table>
            <tr><th>Area</th><th>Location</th><th>Purpose</th></tr>
            <tr><td>Menu bar</td><td>Top</td><td>File, View, Spectra processing, Analysis &amp; Visualization, Help access</td></tr>
            <tr><td>Spectrum list</td><td>Left panel</td><td>Select which spectra to view and process</td></tr>
            <tr><td>Plot canvas</td><td>Centre</td><td>Interactive plot of selected spectra</td></tr>
            <tr><td>Basic plot options</td><td>Bottom toolbar</td><td>Plot type, axis scales, line colours</td></tr>
            <tr><td>Link axes</td><td>Bottom toolbar</td><td>Synchronise x/y axes across subplots (shown only in Grid plot mode)</td></tr>
            <tr><td>Spectra Analysis &amp; Visualization</td><td>Bottom toolbar</td><td>SVD, PCA, NMF, MCR-ALS, cluster analysis, reference matching, band ratio, 2D map, 2D correlation</td></tr>
            <tr><td>Spectra Processing</td><td>Bottom right</td><td>Select, configure and apply operations</td></tr>
            <tr><td>Interactive Update / ☰ Legend</td><td>Below spectrum list</td><td>Live plot refresh toggle; legend control</td></tr>
        </table>

        <!-- ═══════════════════════════════════════════════════════════
             TABLE OF CONTENTS
             ═══════════════════════════════════════════════════════════ -->
        <h2>Contents</h2>
        <ol>
            <li><a href="#import">Data Import &amp; Management</a></li>
            <li><a href="#selection">Spectrum Selection</a></li>
            <li><a href="#visualisation">Visualisation</a>
                <ul>
                    <li><a href="#band-markers">Band Markers</a></li>
                </ul>
            </li>
            <li><a href="#pipeline">Processing Pipeline</a></li>
            <li><a href="#operations">Processing Operations</a>
                <ul>
                    <li><strong>Baseline Correction:</strong>
                        <a href="#baseline">Manual Baseline</a>,
                        <a href="#auto-baseline">Automated Baseline</a>,
                        <a href="#svd-background">SVD Background</a></li>
                    <li><strong>Smoothing:</strong>
                        <a href="#smoothing">SG-Smoothing &amp; FFT Denoising</a></li>
                    <li><strong>Data Manipulation:</strong>
                        <a href="#data-range">Define Spectral Range</a>,
                        <a href="#combine">Combine Spectra</a>,
                        <a href="#subtraction">Interactive Subtraction</a>,
                        <a href="#xaxis">X-Axis Alignment</a>,
                        <a href="#svd-interpolation">SVD Interpolation</a></li>
                    <li><strong>Axis &amp; Unit Conversion:</strong>
                        <a href="#calculator">Spectral Calculator</a>,
                        <a href="#normalization">Normalization</a>,
                        <a href="#cd-unit-conversion">CD Unit Conversion</a>,
                        <a href="#xaxis-unit-conversion">X-axis Unit Conversion</a>,
                        <a href="#mean-centering">Mean-Center Spectra (Dataset)</a></li>
                    <li><strong>Spike Removal:</strong>
                        <a href="#spike">Spike Removal</a>,
                        <a href="#cosmic-ray">Cosmic Ray Detection</a></li>
                    <li><strong>Resolution:</strong>
                        <a href="#resolution">Resolution Enhancement</a></li>
                    <li><a href="#peak-fitting">Peak Fitting</a></li>
                    <li><strong>Batch Pipeline:</strong>
                        <a href="#batch-pipeline">Batch Pipeline Replay</a></li>
                </ul>
            </li>
            <li><a href="#visualisation-analysis">Spectra Analysis &amp; Visualization</a>
                <ul>
                    <li><a href="#svd-analysis">SVD Analysis</a></li>
                    <li><a href="#pca-scores">PCA Scores &amp; Loadings</a></li>
                    <li><a href="#nmf">NMF</a></li>
                    <li><a href="#mcr-als">MCR-ALS</a></li>
                    <li><a href="#reference-matching">Reference Library Matching</a></li>
                    <li><a href="#band-ratio">Band Ratio / Peak Area Calculator</a></li>
                    <li><a href="#melting-curve">Melting Curve Analysis</a></li>
                    <li><a href="#isosbestic-point">Isosbestic / Isodichroic Point Detection</a></li>
                    <li><a href="#cluster">Cluster Analysis</a></li>
                    <li><a href="#2d-map">2D Map</a></li>
                    <li><a href="#2d-correlation">2D Correlation</a></li>
                    <li><a href="#pls">PLS / PLS-DA</a></li>
                    <li><a href="#kinetics-fitting">Kinetics Fitting</a></li>
                    <li><a href="#qc-outlier">QC / Outlier Detection</a></li>
                </ul>
            </li>
            <li><a href="#legend">Legend</a></li>
            <li><a href="#save-export">Saving &amp; Export</a></li>
            <li><a href="#keyboard">Keyboard Shortcuts</a></li>
            <li><a href="#spectroscopy">Spectroscopy-Specific Guidelines</a></li>
            <li><a href="#test-datasets">Test Datasets (known ground truth)</a></li>
            <li><a href="#troubleshooting">Troubleshooting</a></li>
        </ol>

        <!-- ═══════════════════════════════════════════════════════════
             1. DATA IMPORT
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="import">1. Data Import &amp; Management <a href="help://import" style="font-size:8pt; font-weight:normal;">📖 open help</a></h2>

        <h3>Supported File Formats</h3>
        <table>
            <tr><th>Format</th><th>Extension</th><th>Notes</th></tr>
            <tr><td>Plain text</td><td>.txt, .dat, .csv</td><td>Various delimiters auto-detected</td></tr>
            <tr><td>Excel</td><td>.xlsx, .xls</td><td>First sheet, or a sheet named <code>spectra</code> if present — or pick any sheet explicitly via the Sheet dropdown. Tick <strong>Import several sheets</strong> to bring in more than one sheet at once.</td></tr>
            <tr><td>SPE (LightField / WinSpec)</td><td>.spe</td><td>Raman/CCD instrument files — LightField 3.x and legacy WinSpec 2.x, auto-detected; one spectrum per frame, numbered with the same Zero padding setting as text/Excel imports. Pixel-index x-axis by default. Legacy WinSpec files with a recorded x-axis calibration offer an opt-in "Use calibrated x-axis" checkbox (unchecked by default); LightField files and uncalibrated legacy files always get the pixel-index axis, no calibration option; see Import → Help for details</td></tr>
            <tr><td>SPC (Thermo/GRAMS)</td><td>.spc</td><td>Universal Data Format — old and new header variants auto-detected; real calibrated x-axis, one spectrum per subfile (almost always one), multi-subfile files numbered with the same Zero padding setting as text/Excel imports; see Import → Help for details</td></tr>
            <tr><td>JWS (JASCO SpectraManager)</td><td>.jws</td><td>CD spectropolarimeter files (e.g. J-815); calibrated wavelength x-axis. A file can carry several co-recorded channels — commonly CD [mdeg], sometimes also HT [V] and/or Absorbance [AU] — shown in a checkable table so you pick which channel(s) to import; each channel's type is an auto-detected guess with an editable override; see Import → Help for details</td></tr>
            <tr><td>MAT (WITec/Project FIVE map)</td><td>.mat</td><td>Hyperspectral Raman/IR map export — one spectrum per pixel of the map's row x col grid, all sharing the map's own calibrated x-axis; row/col position and (when recorded) physical µm coordinates are attached to every spectrum's metadata; see Import → Help for details</td></tr>
            <tr><td>Standard layout</td><td>any</td><td>First column = shared x-scale, remaining columns = one spectrum each (the default)</td></tr>
            <tr><td>Interlaced layout</td><td>any</td><td>Alternating x,y pairs (x1,y1,x2,y2…) — each spectrum has its own x-scale column</td></tr>
            <tr><td>Row-oriented layout</td><td>any</td><td>The mirror of Standard — first row = shared x-scale, remaining rows = one spectrum each</td></tr>
        </table>

        <div class="tip">
            <strong>Unrecognized extension?</strong> Not rejected on the name alone —
            if its content looks like numeric columns (the same check plain text
            files get), you're asked whether to read it as text data anyway. Useful
            for instrument or collaborator files saved under some other extension
            (<code>.bcw</code>, etc.) that are really just ordinary x/y columns. Pick
            <strong>All Files</strong> in the file-picker's format dropdown, or drag
            the file onto the window, to reach one. Doesn't apply to SPE/SPC/JWS or
            Excel, which always need their real extension.
        </div>

        <h3>Import Methods</h3>
        <ul>
            <li><strong>File → Import data → new:</strong> Replace all current spectra. If every selected file fails to import, existing spectra are left untouched — nothing is cleared until at least one new file has actually loaded successfully.</li>
            <li><strong>File → Import data → add:</strong> Append to existing spectra</li>
            <li><strong>Drag and drop:</strong> drag spectrum files from your file manager and drop them anywhere on the application window — opens the same Import dialog with those files already selected. If spectra are already loaded it first asks whether to <strong>Add</strong> (keep them) or <strong>Replace all</strong>; <strong>Add</strong> is the default, so a stray drag can never discard your work. The same prompt appears for the built-in datasets under Help → Test datasets.</li>
        </ul>

        <div class="screenshot">
            <img src="$IMPORT_DIALOG" width="$IMPORT_DIALOG_W" height="$IMPORT_DIALOG_H" alt="Import Spectra dialog with file list, Separators, General (Layout and column pickers), and Preview groups" />
            <p class="caption">The Import Spectra dialog: Separators and General settings (Layout, column pickers, zero padding, header threshold) side by side at the top, with a live Preview of the currently-selected file below. Each file in a multi-file import can be configured independently.</p>
        </div>

        <h3>Auto-Detection</h3>
        <p>The importer automatically detects delimiter, decimal separator, header rows,
        and Layout (Standard / Interlaced / Row-oriented). Override any of these per file
        directly in the Import dialog.</p>

        <table>
            <tr><th>Setting</th><th>Options</th><th>Description</th></tr>
            <tr><td>Sheet</td><td>Auto / any sheet name</td><td>Excel files only — which worksheet to read. "Import several sheets" turns this into a checklist so several can be read in one pass; their spectra are labelled <code>file [sheet] : column</code> so identically-named columns stay distinct. <strong>Each sheet keeps its own settings</strong> — click a sheet in the list to configure it (tick = import it, click = configure it).</td></tr>
            <tr><td>Value separator</td><td>Auto, ; tab , | space</td><td>Column delimiter</td></tr>
            <tr><td>Decimal separator</td><td>Auto . ,</td><td>Decimal point character</td></tr>
            <tr><td>Header row</td><td>Auto Yes No</td><td>Whether row 1 (or, in Row-oriented, column 1) contains labels</td></tr>
            <tr><td>Header threshold</td><td>1–100%</td><td>How strict Auto header detection is — % of non-numeric tokens required to call it a header</td></tr>
            <tr><td>Layout</td><td>Standard / Interlaced / Row-oriented</td><td>Which of the three layouts above the file uses</td></tr>
            <tr><td>Label column</td><td>Row-oriented only</td><td>Which raw-file column supplies spectrum names, if not the first</td></tr>
            <tr><td>X-scale column</td><td>Standard only</td><td>Which raw-file column is the shared x-scale, if not the first</td></tr>
            <tr><td>Exclude columns</td><td>Standard only</td><td>Metadata columns (ID, sample type, timestamp…) to drop entirely rather than misread as spectra. Columns the header row doesn't name are listed too, as <code>Column N: (no name)</code>, so they can be excluded as well</td></tr>
            <tr><td>Use row number as X axis</td><td>Any layout</td><td>For tables with no meaningful numeric X axis (e.g. concentration profiles). Uses 1, 2, 3, … as X so that <em>every</em> remaining column (or row) stays a spectrum instead of one being eaten as the axis</td></tr>
            <tr><td>Zero padding</td><td>1–10 digits</td><td>Width of auto-generated spectrum numbers — also applies to multi-frame SPE and multi-subfile SPC files, the only general setting those two formats share with text/Excel imports</td></tr>
        </table>

        <div class="info">
            <strong>Ascending X-axis is automatic, not a setting.</strong> Every
            imported spectrum is reordered so X ascends — purely cosmetic, no value
            is changed, each y stays with its x — for every file and every layout.
            There's no checkbox for it; it always happens. If the same x-value
            appears more than once after sorting, those points are additionally
            <strong>merged</strong> (averaged) so x stays a valid one-value-per-point
            axis — this part does change the data, and you're warned about it both
            in the Import Results summary and the application log whenever it
            happens. See <a href="help://import">the full Import help</a> for the
            complete explanation, including how to recover the pre-merge values from
            a spectrum's metadata.
            <br><br>
            <strong>Exception — repeated-scan data:</strong> if most of a spectrum's
            x-values repeat the <em>same</em> number of times S (2 or more) — a
            forward/reverse sweep sharing an x-axis, or several spectra concatenated
            in one long column pair — that's too consistent to be coincidental
            duplication, so instead of merging silently you're asked, once per file:
            <strong>split into S spectra</strong> (keeping every scan separate) or
            <strong>merge</strong> (the default above, unchanged). The ordinary case —
            no such pattern, or just a stray duplicate or two — is never affected by
            this and merges silently exactly as described above.
        </div>

        <div class="tip">
            <strong>Importing several files at once:</strong> every setting above can be
            different for each file in a multi-file selection — a batch can freely mix a
            Standard-layout file, an Interlaced file, and a Row-oriented file, each with
            its own delimiter and header settings. A scrollable list shows every selected
            file; click any entry to preview and adjust that file specifically. A file's
            settings are remembered for the rest of the dialog session once you've
            previewed it, and files you never click into are simply auto-detected.
            <strong>Reset to Auto-detected</strong> undoes manual changes for the current
            file; <strong>Apply to All Other Files</strong> copies the current file's
            settings onto the rest of the batch at once — handy when many files share the
            same non-default format. For a format you import repeatedly across different
            projects, an <strong>Import Profile</strong> saves the same kind of settings
            snapshot under a name, persisted on disk so it's still available the next
            time you open Import — not just for the rest of this session.
        </div>

        <div class="info">
            <strong>Choosing the right Layout matters.</strong> The app always stores
            spectra internally the same way (one x-scale + one y-scale per spectrum) no
            matter which Layout you import with — but picking the wrong one for a given
            file doesn't produce an error, it produces plausible-looking wrong numbers.
            See <a href="help://import">the full Import help</a> for a longer explanation,
            including why this also matters for analyses like PCA.
        </div>

        <h3>Spectrum Naming</h3>
        <ul>
            <li>File + column header if header exists: <em>sample : Peak1</em></li>
            <li>File + sequential number if no header: <em>sample : 0001</em></li>
            <li>File name only for single-spectrum files</li>
        </ul>
        <p>Rename any spectrum via right-click → Rename, or use
        <strong>View → Rename spectra</strong>.</p>

        <div class="info">
            <strong>Renaming is always safe.</strong> Every spectrum is tracked
            internally by a permanent identifier, not by its display name, so anything
            attached to a spectrum — baseline points, per-spectrum custom settings,
            stored subtraction factors — follows it automatically through a rename, no
            matter how many times you rename it. A rename also appears as its own
            entry in Operations History, the same as any other operation — so older
            history entries always keep showing whichever name was in use at that
            earlier point, and jumping back in time always shows you the name a
            spectrum genuinely had then, never a name it received later. Every rename
            is also recorded in the spectrum's own metadata (right-click →
            <strong>Show Metadata</strong>, under Correction History), showing exactly
            what it was renamed from and to — if a spectrum has been renamed more than
            once, its full naming history is visible there, in order.
        </div>

        <div class="tip">
            <strong>Batch renames stay grouped.</strong> If you rename several
            spectra at once, the same "renamed from / to" tracking applies to
            each of them individually — every spectrum keeps its own accurate
            history regardless of how many others were renamed alongside it.
        </div>

        <h3>Spectrum List Context Menu (right-click on list)</h3>
        <p>Right-clicking on the spectrum list opens a context menu. Right-clicking
        never changes your current selection — if something is already selected, it
        stays selected regardless of where exactly you right-click; a right-click only
        selects the clicked item if nothing was selected yet.</p>

        <div class="screenshot">
            <img src="$SPECTRUM_LIST_CONTEXT_MENU" width="$SPECTRUM_LIST_CONTEXT_MENU_W" height="$SPECTRUM_LIST_CONTEXT_MENU_H" alt="Spectrum list right-click context menu" />
            <p class="caption">The spectrum list's right-click context menu.</p>
        </div>

        <table>
            <tr><th>Item</th><th>Description</th></tr>
            <tr><td><strong>Show Metadata</strong></td><td>Display metadata for the currently highlighted spectrum.</td></tr>
            <tr><td><strong>Plot Properties</strong></td><td>A submenu with three actions: <strong>Show Info</strong> (current colour/style for the selected spectra), <strong>Modify</strong> (change colour/line style), and <strong>Reset to default</strong>.</td></tr>
            <tr><td><strong>Select All</strong></td><td>Select all spectra</td></tr>
            <tr><td><strong>Unselect All</strong></td><td>Deselect all spectra</td></tr>
            <tr><td><strong>Select spectra</strong></td><td>Open a dialog to select spectra by name pattern</td></tr>
            <tr><td><strong>Rename</strong></td><td>Rename the selected spectrum/spectra. The list is re-sorted afterward, since a new name can change where a spectrum belongs alphabetically.</td></tr>
            <tr><td><strong>Copy spectra</strong></td><td>Create copies of the selected spectra with a <em>_copy</em> suffix (also <strong>Ctrl+C</strong> or <strong>Ctrl+V</strong> — see below). Useful for comparing a spectrum before and after an operation. The copy operation is recorded in the Operations History so it can be undone by jumping to the previous state. The list is re-sorted afterward and the copies are selected. No confirmation is asked — a copy never removes or changes anything, so there's nothing to confirm.</td></tr>
            <tr><td><strong>Delete spectra</strong></td><td>Remove the selected spectra from the list (also <strong>Ctrl+D</strong> or the <strong>Delete</strong> key — see below). Asks for confirmation first, since this visibly removes spectra from the list you're looking at — even though it's also recorded in the Operations History, so jumping to the previous state restores them if you ever need to.</td></tr>
        </table>

        <div class="tip">
            <strong>Buttons above the list:</strong> <strong>Select All</strong>,
            <strong>Unselect All</strong>, and <strong>Select spectra</strong> sit directly
            above the spectrum list, and <strong>Rename</strong>, <strong>Show Metadata</strong>,
            and <strong>Plot Properties</strong> sit in a row just below them — all five do
            exactly the same thing as their context-menu equivalents, just without needing a
            right-click. <strong>Copy spectra</strong> and <strong>Delete spectra</strong> are
            <em>not</em> buttons — they're reached via keyboard shortcut instead
            (<strong>Ctrl+C</strong>/<strong>Ctrl+V</strong> to copy,
            <strong>Ctrl+D</strong>/<strong>Delete</strong> to delete), or still available from
            the right-click context menu if you prefer.
        </div>

        <div class="screenshot">
            <img src="$SPECTRUM_LIST" width="$SPECTRUM_LIST_W" height="$SPECTRUM_LIST_H" alt="Spectrum list panel with Select All, Unselect All, Select spectra buttons above and Rename, Show Metadata, Plot Properties below" />
            <p class="caption">The two button rows above the spectrum list: Select All / Unselect All / Select spectra, and Rename / Show Metadata / Plot Properties.</p>
        </div>

        <div class="screenshot">
            <img src="$RENAME_DIALOG" width="$RENAME_DIALOG_W" height="$RENAME_DIALOG_H" alt="Rename Spectra dialog with an editable table of original and new labels" />
            <p class="caption">The Rename Spectra dialog: original labels on the left, editable new labels on the right. Right-click selected rows for prefix/suffix, sequential rename, or find-and-replace.</p>
        </div>

        <div class="screenshot">
            <img src="$METADATA_DIALOG" width="$METADATA_DIALOG_W" height="$METADATA_DIALOG_H" alt="Spectrum metadata dialog showing a formatted table of metadata fields" />
            <p class="caption">Show Metadata for a single spectrum: every stored field, including nested values, formatted as a readable table. The <strong>Copy screenshot</strong> button next to Close copies an image of the current view to the clipboard — handy for pasting into a lab notebook, email, or bug report without the recipient needing this app open.</p>
        </div>

        <div class="screenshot">
            <img src="$METADATA_TABLE_DIALOG" width="$METADATA_TABLE_DIALOG_W" height="$METADATA_TABLE_DIALOG_H" alt="Metadata table dialog listing multiple spectra with a Show Details button" />
            <p class="caption">Metadata for several spectra at once: double-click a row, or select it and click Show Details, to open the full single-spectrum view above.</p>
        </div>

        <div class="tip">
            <strong>Copy before processing:</strong> use Copy spectra (or Ctrl+C/Ctrl+V) before applying an
            operation to keep the original for comparison. Both the original and the copy
            will be available in the list simultaneously, so you can select both and use
            an overlay plot to compare before and after.
        </div>

        <h3>Shorten Names</h3>
        <p>The <strong>Shorten names</strong> checkbox (next to the spectrum list) strips
        whatever text is common to every currently-listed spectrum's name — usually a shared
        file-name prefix or suffix — so only the part that actually distinguishes them is
        shown. It looks for several distinct groups independently (e.g. one import's worth
        of "CD spectra with header : ..." names alongside a separate import's worth of "Raman
        spectra - no header : ..." names), rather than requiring one prefix/suffix shared by
        the whole list.</p>
        <div class="info">
            <strong>Display-only, never identity.</strong> Shortening only changes what is
            <em>shown</em>. Selection, exported file names, saved data, and anything else
            that depends on a spectrum's real name always use the full original label —
            shortening is purely cosmetic and instant to toggle on/off. The main window's
            checkbox applies to the main spectrum list and plot legends/axis labels only.
            Toggling it updates the current plot immediately, with no need to press
            Refresh Plot.
        </div>
        <div class="info">
            <strong>Each analysis dialog has its own, separate checkbox.</strong> Cluster
            Analysis, 2D Correlation, Reference Library Matching, Band Ratio, NMF and
            MCR-ALS concentration/scores plots, Melting Curve Analysis, SVD Analysis's
            "Spectrum labels" x-axis option, and every processing operation dialog show
            their own <strong>Shorten names</strong> checkbox rather than sharing the main
            window's. Each one starts unchecked when the dialog opens, regardless of the
            main window's setting, and toggling the main window's checkbox has no effect on
            an already-open dialog (or vice versa) — set the option in whichever window you
            want shortened names in.
        </div>

        <!-- ═══════════════════════════════════════════════════════════
             2. SPECTRUM SELECTION
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="selection">2. Spectrum Selection</h2>

        <p>The left-hand list shows all imported spectra. Selected spectra are
        highlighted in <strong>red</strong> and plotted on the canvas.</p>

        <table>
            <tr><th>Action</th><th>How</th></tr>
            <tr><td>Select one spectrum</td><td>Click &mdash; selects the clicked item and
                deselects everything else</td></tr>
            <tr><td>Select a contiguous range</td><td><strong>Shift+click</strong> the last item
                in the range &mdash; extends the selection from the last-clicked item to the
                target, exactly like selecting rows in Excel or a file manager.
                The existing selection is preserved.</td></tr>
            <tr><td>Toggle one item</td><td><strong>Ctrl+click</strong> &mdash; adds an item to the
                selection without deselecting others, or removes it if already selected</td></tr>
            <tr><td>Drag to select</td><td>Hold the left mouse button and drag across multiple items</td></tr>
            <tr><td>Select all</td><td><strong>Select All</strong> button or
                <span class="kbd">Ctrl+A</span></td></tr>
            <tr><td>Deselect all</td><td><strong>Unselect All</strong> or
                <span class="kbd">Ctrl+U</span></td></tr>
            <tr><td>Select by range / pattern</td><td><strong>Select spectra</strong> button
                (or right-click &rarr; <strong>Select spectra</strong>)
                &mdash; opens a dialog to select by index range with step</td></tr>
            <tr><td>Sort order</td><td>Natural (numeric-aware) order by label. Tick
                <strong>reverse sorting</strong>, just above the list next to the
                spectrum counter, to flip the order.</td></tr>
        </table>

        <div class="info">
            <strong>Sort order is "natural," not plain alphabetical — embedded
            numbers compare numerically, not character-by-character.</strong>
            A label is split into alternating text/number chunks, and each number
            chunk is compared as an integer rather than as text. So
            <code>spectrum 4</code> now sorts <em>before</em>
            <code>spectrum 39</code> and <code>spectrum 40</code>, not between them
            the way plain text order would place it — you don't need to
            zero-pad numbers in your labels just to get a sensible order any
            more. This also nests correctly across several numbers in the same
            label (e.g. <code>run2_T=9.5</code> sorts before
            <code>run2_T=100.0</code>, which sorts before
            <code>run10_T=1.0</code>) and is case-insensitive for the text parts,
            exactly like the old sort was. If a label has no digits in it at
            all, none of this changes anything — it's just plain
            alphabetical, identical to before.
        </div>

        <div class="info">
            <strong>There's no way to pin a custom order that isn't derivable
            from the label itself.</strong> The list is fully rebuilt in
            sorted order after essentially anything you do — import, rename,
            copy, running an operation — so there's no drag-and-drop
            reordering, and any manual arrangement wouldn't survive the next
            action anyway. If you want spectra in a specific order for
            reasons unrelated to alphabetical/numeric order, the only lever
            is renaming them (or adding a numeric prefix) so the labels
            themselves sort into the order you want.
        </div>

        <div class="warning">
            <strong>One edge case: a minus sign is only read as "negative" when
            it isn't glued onto a preceding letter or digit.</strong> This
            distinguishes a genuine negative value — e.g. a sub-zero temperature
            like <code>T=-5.00C</code>, where the <code>-</code> follows
            <code>=</code> — from a hyphen used as a separator, e.g.
            <code>sample-1</code>, <code>sample-2</code>, <code>sample-10</code>,
            where the <code>-</code> follows a letter and is treated as plain
            text so those three still sort in count order (1, 2, 10) rather than
            as if they were the numbers &minus;1, &minus;2, &minus;10 (which would
            sort 10, 2, 1). If your labels mix both patterns, this heuristic
            resolves them independently and correctly in the same list — verified
            directly, not just assumed.
        </div>

        <div class="info">
            Zero-padding your labels is no longer necessary for correct sort
            order, but it's still available and still useful for readability
            and for keeping generated names a consistent width: see Import's
            <strong>Zero Padding</strong> setting (<a href="help://import">Import
            help</a>) — the Preview table shows the exact padded numbers you'll
            get before you import.
        </div>

        <div class="screenshot">
            <img src="$SELECTION_DIALOG" width="$SELECTION_DIALOG_W" height="$SELECTION_DIALOG_H" alt="Select Spectra dialog with Start, End, Step fields and Select, Add to Selection, Remove from Selection buttons" />
            <p class="caption">The Select Spectra dialog: pick a start/end index and step, then Select, Add to Selection, or Remove from Selection.</p>
        </div>

        <div class="tip">
            <strong>Typical workflow for selecting a block:</strong> click the first spectrum
            in the group, then Shift+click the last one &mdash; all spectra between them are
            selected instantly.  Use Ctrl+click afterwards to add or remove individual
            spectra from the selection without losing the rest.
        </div>

        <div class="tip">
            <strong>Processing applies to selected spectra.</strong> Always verify your
            selection (and the counter above the list) before committing an operation.
        </div>

        <p>The counter above the list (e.g. <em>19/28</em>) shows selected / total.</p>

        <!-- ═══════════════════════════════════════════════════════════
             3. VISUALISATION
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="visualisation">3. Visualisation</h2>

        <h3>Plot Types</h3>
        <table>
            <tr><th>Mode</th><th>Description</th></tr>
            <tr><td><strong>Single spectrum</strong></td><td>Display one spectrum at a time.
                Switching to this mode automatically clears any multi-selection and selects
                just the first spectrum in the list, since only one can be shown.</td></tr>
            <tr><td><strong>Overlay plot</strong></td><td>All selected spectra on one set of axes, colour-coded</td></tr>
            <tr><td><strong>Grid plot</strong></td><td>Each spectrum in its own subplot; rows and columns
                configurable via the <em>nrow</em> / <em>ncol</em> spinboxes.
                Axes can be linked across rows, columns, or all subplots.</td></tr>
            <tr><td><strong>Waterfall plot</strong></td><td>Spectra stacked with a fixed vertical offset so
                every spectrum is visible without overlap. Set the <em>Offset</em> spinbox to
                <em>auto</em> (value&nbsp;=&nbsp;0) for automatic scaling (10&nbsp;% of the
                peak-to-peak range of the largest spectrum), or enter a fixed value in
                data units for uniform spacing.</td></tr>
            <tr><td><strong>Mean &plusmn; SD</strong></td><td>Plots the mean spectrum as a thick line with a
                shaded &plusmn;1&nbsp;standard-deviation band. Tick <em>Show individual spectra</em>
                to overlay the individual measurements as thin faded lines behind the mean &mdash;
                useful for quickly spotting outliers and identifying which spectral regions are
                reproducible. All selected spectra must share the same x-axis length; any that
                differ are excluded and flagged in the plot title.</td></tr>
            <tr><td><strong>Difference</strong></td><td>Each selected spectrum minus a reference
                (group mean or a chosen spectrum). Choose the reference in the <em>Reference</em>
                dropdown. The reference spectrum is hidden by default; tick <em>Show reference</em>
                to overlay it (dashed) alongside the difference curves. A dotted zero line is
                always shown for orientation.
                Useful for quality control and detecting processing artefacts.</td></tr>
            <tr><td><strong>Heatmap</strong></td><td>False-colour intensity image: x-axis
                = wavenumber, y-axis = spectrum index, colour = intensity. The colour range
                is clipped to the 2nd&ndash;98th percentile so features remain visible even
                with a large fluorescence background. Choose a <em>Colormap</em> and
                <em>Interpolation</em> from the dropdowns. Ideal for large datasets
                (hundreds to thousands of spectra) to reveal trends, outliers, and cosmic
                rays at a glance.</td></tr>
        </table>

        <div class="screenshot">
            <img src="$PLOT_OVERLAY" width="$PLOT_OVERLAY_W" height="$PLOT_OVERLAY_H" alt="Overlay plot of several spectra on one set of axes" />
            <p class="caption">Overlay plot: all selected spectra on one set of axes, colour-coded.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_GRID" width="$PLOT_GRID_W" height="$PLOT_GRID_H" alt="Grid plot with each spectrum in its own subplot" />
            <p class="caption">Grid plot: each spectrum in its own subplot, arranged by the nrow / ncol spinboxes.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_WATERFALL" width="$PLOT_WATERFALL_W" height="$PLOT_WATERFALL_H" alt="Waterfall plot with spectra stacked using a vertical offset" />
            <p class="caption">Waterfall plot: spectra stacked with a fixed vertical offset, useful for visualising trends across a series.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_MEAN_SD" width="$PLOT_MEAN_SD_W" height="$PLOT_MEAN_SD_H" alt="Mean plus or minus one standard deviation band plot" />
            <p class="caption">Mean &plusmn; SD: the mean spectrum with a shaded &plusmn;1 standard-deviation band; individual replicates can be overlaid faintly behind it.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_DIFFERENCE" width="$PLOT_DIFFERENCE_W" height="$PLOT_DIFFERENCE_H" alt="Difference plot of spectra minus a reference spectrum" />
            <p class="caption">Difference plot: each selected spectrum minus a chosen reference, with a dotted zero line for orientation.</p>
        </div>

        <div class="screenshot">
            <img src="$PLOT_HEATMAP" width="$PLOT_HEATMAP_W" height="$PLOT_HEATMAP_H" alt="Heatmap of spectral intensity with wavenumber on x-axis and spectrum index on y-axis" />
            <p class="caption">Heatmap: false-colour intensity image across all spectra at once, ideal for spotting trends and outliers in large datasets.</p>
        </div>

        <div class="tip">
            <strong>When to use each mode:</strong><br>
            <em>Overlay</em> &mdash; comparing a small number of spectra directly.<br>
            <em>Grid</em> &mdash; systematic inspection of many spectra individually.<br>
            <em>Waterfall</em> &mdash; visualising trends across a series (time, concentration, temperature).<br>
            <em>Mean &plusmn; SD</em> &mdash; quality-control check on replicates; summarising a group.<br>
            <em>Difference</em> &mdash; detecting spectral changes between samples or introduced by processing.<br>
            <em>Heatmap</em> &mdash; overview of all spectra simultaneously; spotting trends and outliers in large datasets.
        </div>

        <h3>Axis Controls</h3>
        <ul>
            <li><strong>X-scale / Y-scale:</strong> Linear or logarithmic</li>
            <li><strong>Link x-axes / Link y-axes:</strong> Synchronise zoom across subplots
                (Grid plot only &mdash; the Link axes box is hidden for other plot types)</li>
            <li><strong>Automatic line colors:</strong> Assign distinct colours automatically
                (sits directly below the plot-type dropdown in Basic plot options)</li>
        </ul>

        <h3 id="band-markers">Band Markers</h3>
        <p>Click <strong>Band markers&hellip;</strong> in the Basic plot options panel to
        open the Band Marker Manager. Named reference lines are drawn on <em>all</em> plot
        modes simultaneously and persist for the session. Each marker is either an
        <strong>X marker</strong> (a vertical line marking an x-value, e.g. a band
        position) or a <strong>Y marker</strong> (a horizontal line marking a y-value,
        e.g. a threshold) &mdash; set independently for every marker via its
        <em>Axis</em> column. The dialog has its own dedicated
        <a href="help://band_markers">Band Markers help page</a> (also reachable via its
        own Help button) with full detail; this section is a quick summary.</p>

        <div class="screenshot">
            <img src="$BAND_MARKERS" width="$BAND_MARKERS_W" height="$BAND_MARKERS_H" alt="Band Marker Manager dialog with a table of named vertical and horizontal line markers" />
            <p class="caption">The Band Marker Manager: a table of named markers, each with its own position, axis (X or Y), label, style, width, font size, label offset, label direction, and colour — double-click any cell to edit it, or select a row to load it into the fields below.</p>
        </div>

        <ul>
            <li>Enter a position, choose <strong>Axis</strong> (X for a vertical line at
                that x-value, Y for a horizontal line at that y-value), a label (e.g.
                <em>Phe 1004</em>), line style, line width, font size, label offset,
                label direction, and colour, then click <strong>Add</strong> &mdash;
                the plot updates immediately</li>
            <li><strong>Editing an existing marker:</strong> double-click any cell in
                the table to edit it in place &mdash; position, label, width, font
                size, and label offset type directly; axis, line style, label
                direction, colour, and visibility open their own picker instead. Or
                select a row to load it into the bottom row, adjust any field, and
                click <strong>Update selected</strong> (<strong>Cancel edit</strong>
                discards the change instead). The marker stays selected after clicking
                Update, so a second or third tweak to the same marker doesn't need
                reselecting it from the table each time — and adjusting the bottom
                row's own fields never drops the selection either, even if it briefly
                looks that way while the table doesn't have the keyboard focus.</li>
            <li><strong>Editing several markers at once:</strong> select 2 or more rows
                (Ctrl+click, or drag) to load Style, Width, Font size, Label offset,
                Label direction, Colour, and Axis into the bottom row for a bulk edit
                — the button changes to <strong>Update N selected</strong>. Position
                and Label are disabled in this mode, since setting several markers to
                the identical position or label text wouldn't make sense; adjust
                whichever of the remaining fields should apply to the whole batch and
                click Update. The batch stays selected afterward, the same way a
                single-row edit does.</li>
            <li>Remove individual markers (or a selected batch) or clear all from the
                table</li>
            <li>The global <em>Show all band markers on plots</em> checkbox
                hides/shows every marker at once without deleting them; each marker
                also has its own <em>Visible</em> column to hide just that one</li>
            <li><strong>Label direction</strong> sets how a marker's label is drawn
                (independently of its Axis): <em>Vertical</em> (the default) reads
                bottom-to-top alongside the line and takes almost no space along the
                line; <em>Horizontal</em> is easier to read but takes more room and can
                run into a neighbouring marker if two are close together</li>
            <li><strong>Label offset</strong> (its own column / bottom-row field, per
                marker) sets how far down from the top of the plot <em>that
                marker's</em> label starts, as a percentage (0&ndash;100%) of the
                y-axis range &mdash; increase it if a label collides with the y-axis's
                top tick number or scientific-notation exponent. For a Y marker this is
                measured from the right edge instead, by symmetry. Since it's set per
                marker, different markers can use different offsets, e.g. to stack
                labels at different heights when several sit close together.</li>
            <li><strong>Label offset from line</strong>, top-right of the dialog, is
                the one remaining setting shared by every marker: the gap, in points,
                between a marker's line and the start of its label &mdash; increase it
                if the line itself crosses through the label's characters.</li>
        </ul>
        <div class="tip">Band markers also appear in external figure windows opened via
        right-click &rarr; Open in New Window.</div>

        <h3>Navigation Toolbar</h3>
        <p>The matplotlib toolbar (below the plot) provides: Home, Back, Forward, Pan,
        Zoom, Axis properties, Curve properties, and Save figure.</p>

        <h3>Context Menu (right-click on plot)</h3>
        <p>Right-clicking anywhere on the plot canvas opens a context menu with the
        following options:</p>

        <div class="screenshot">
            <img src="$PLOT_CONTEXT_MENU" width="$PLOT_CONTEXT_MENU_W" height="$PLOT_CONTEXT_MENU_H" alt="Plot canvas right-click context menu" />
            <p class="caption">The plot canvas's right-click context menu.</p>
        </div>

        <table>
            <tr><th>Item</th><th>Description</th></tr>
            <tr><td><strong>Detect Peaks</strong></td><td>Automatically detect and mark peaks on the currently plotted spectra</td></tr>
            <tr><td><strong>Clear Peaks</strong></td><td>Remove all peak markers from the plot</td></tr>
            <tr><td><strong>Legend</strong></td><td>Open the Legend Properties dialog (same as the ☰ Legend button below the spectrum list)</td></tr>
            <tr><td><strong>Grid</strong></td><td>Configure grid lines (on/off, style, colour)</td></tr>
            <tr><td><strong>Layout Properties</strong></td><td>Adjust subplot spacing and constrained layout settings</td></tr>
            <tr><td><strong>Axis properties</strong></td><td>Set axis labels, tick marks, and limits</td></tr>
            <tr><td><strong>Automatic Line Colors</strong></td><td>Toggle automatic colour assignment for plotted lines (✓ = enabled)</td></tr>
            <tr><td><strong>Default Points</strong></td><td>Toggle point markers on spectral lines</td></tr>
            <tr><td><strong>Open in New Window</strong></td><td>Open the current plot in a separate full matplotlib window — use this for publication-quality export (PNG, PDF, SVG, EPS)</td></tr>
        </table>

        <h3 id="legend-panel">Legend</h3>
        <p>The <strong>☰ Legend</strong> button (below the spectrum list) opens the
        Legend Properties dialog. Legend is <strong>disabled by default</strong> to
        avoid performance issues with large datasets. Enable it and configure font,
        position, number of columns, and max items there.</p>
        <div class="warning">
            <strong>Performance tip:</strong> with &gt;50 spectra in overlay or
            waterfall mode, keep the legend disabled — rendering hundreds of entries
            significantly slows down plotting and the result is unreadable anyway.
            Exception: <strong>Grid plot</strong> — the legend is the only way to
            identify which panel belongs to which spectrum, so enable it whenever
            you use Grid plot mode.
        </div>
        <p>See the <a href="help://plot_controls">Interactive Update &amp; Legend
        Performance Guide</a> for a full decision table.</p>

        <h3>Interactive Update</h3>
        <p>When <strong>Interactive Update</strong> is checked, the plot redraws
        automatically on every selection change. This is convenient for small datasets
        (&lt;200 spectra) but can make the application feel unresponsive with large ones
        — every click triggers a full matplotlib render.</p>
        <p>Uncheck <strong>Interactive Update</strong> when working with large datasets.
        The plot clears on selection change and redraws only when you press
        <strong>Refresh Plot</strong> — letting you build the full selection first,
        then render once.</p>
        <p>The <strong>?</strong> button next to the Legend button opens a concise
        guide explaining when to use each setting and how plot type affects performance.
        See also: <a href="help://plot_controls">Interactive Update &amp; Legend
        Performance Guide</a>.</p>

        <!-- ═══════════════════════════════════════════════════════════
             4. PROCESSING PIPELINE
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="pipeline">4. Processing Pipeline</h2>

        <p>All data processing is done through the <strong>Spectra Processing</strong>
        panel at the bottom right of the main window, or equivalently through the
        <strong>Spectra processing</strong> menu in the main menu bar — both lead to
        exactly the same dialogs. The pipeline is:</p>

        <div class="screenshot">
            <img src="$PIPELINE_PANEL" width="$PIPELINE_PANEL_W" height="$PIPELINE_PANEL_H" alt="Spectra Processing panel with operation dropdown and Run, History, question mark buttons" />
            <p class="caption">The Spectra Processing panel: choose an operation from the dropdown, then Run, History, or the ? help button.</p>
        </div>

        <div class="pipeline">
            <strong>Step 1 — Select operation:</strong> Choose from the dropdown
            (grouped by category: Baseline Correction, Smoothing, Data Manipulation,
            Axis &amp; Unit Conversion, Spike Removal, Resolution).<br><br>
            <strong>Step 2 — Run:</strong> Click <strong>Run</strong> to
            open the settings dialog for the chosen operation. Define all parameters.<br><br>
            <strong>Step 3 — Commit:</strong> every operation in the dropdown has its own
            <strong>Apply</strong> and <strong>Add as New</strong> buttons right inside that
            dialog. Apply replaces the selected spectra with the result; Add as
            New keeps the originals untouched and adds the result under a new name (e.g.
            <span class="fm">samplename_normalized</span>, with a number appended on
            collision). Either way, the dialog closes automatically once the commit
            succeeds.<br><br>
            <strong>Step 4 — Review:</strong> Click <strong>History</strong> to see
            the full ordered list of all operations applied, with their parameters.
        </div>

        <div class="tip">
            <strong>Menu bar shortcut:</strong> the same categories and operations
            (Baseline Correction, Smoothing, Data Manipulation, Axis &amp; Unit
            Conversion, Spike Removal, Resolution) are also available from the
            <strong>Spectra processing</strong>
            menu in the main menu bar — selecting one there opens its settings dialog
            directly, the same dialog Step 2 above opens, just without needing to use
            the dropdown first. This mirrors how <strong>Band Ratio</strong>,
            <strong>Reference Matching</strong>, and <strong>Peak Fitting</strong> are
            already reachable from the <strong>Analysis &amp; Visualization</strong>
            menu as well as their own groupbox.
        </div>

        <div class="tip">
            <strong>Settings persistence:</strong> parameter settings (normalization
            regions, spectral ranges, subtraction factors, etc.) are remembered between
            Run sessions, even if you close the dialog without clicking Apply or Add
            as New. If you change the spectrum selection, most operations still show the
            last-used settings — ready to reuse or adjust.
        </div>

        <h3>Operations Are Incremental</h3>
        <p>Each Apply adds one step to the processing history. The History dialog
        shows the complete ordered chain. You can undo steps via the snapshot system
        (see <a href="#save-export">Saving &amp; Export</a>).</p>

        <h3 id="history">Operations History</h3>
        <p>The <strong>History</strong> button opens the <em>Operations History</em>
        dialog, which shows every operation applied in the current session as a
        numbered chain: #0 Original State, #1 first operation, #2 second operation,
        and so on. The currently active state is marked <strong>ACTIVE</strong> in
        green.</p>

        <div class="screenshot">
            <img src="$HISTORY_DIALOG" width="$HISTORY_DIALOG_W" height="$HISTORY_DIALOG_H" alt="Operations History dialog with a numbered chain of applied operations" />
            <p class="caption">The Operations History dialog: a numbered chain of every applied operation, with the active state highlighted in green.</p>
        </div>

        <p>The history tracks <em>all</em> state-changing actions, not just processing
        operations. This includes:</p>
        <ul>
            <li>All processing operations (Normalization, Smoothing, Baseline, etc.)</li>
            <li><strong>Delete spectra</strong> — removing spectra is recorded; jump back to restore them</li>
            <li><strong>Copy spectra</strong> — adding copies is recorded; jump back to remove them</li>
        </ul>

        <div class="info">
            <strong>Renaming and history:</strong> renaming a spectrum creates its own
            entry in the chain, just like any other operation — it never reaches back
            to change an earlier entry. So an older entry always keeps showing
            whichever name a spectrum had at that point in time, and jumping back in
            history always shows the name that was genuinely true then.
        </div>

        <p>Each entry has two buttons:</p>
        <ul>
            <li><strong>Spectra List</strong> — which spectra were processed</li>
            <li><strong>Parameters</strong> — the exact settings used. Settings that
                are the same for every spectrum are shown once, as plain text; only
                a setting that genuinely differs from one spectrum to the next (e.g.
                Normalization's factor) appears as a per-spectrum table, with a
                <strong>Copy to Clipboard</strong> button for pasting into a
                spreadsheet or report. If every setting is identical, there's no
                table at all — just the settings.</li>
        </ul>

        <h4>Jumping to a Previous State</h4>
        <p>Select any entry and click <strong>Jump to Selected State</strong> to
        restore the data to how it looked immediately after that operation. This
        is the primary undo mechanism within a session.</p>

        <div class="warning">
            <strong>No branches:</strong> if you jump back to an earlier state and
            then Apply a new operation, all operations that originally came after
            the jumped-to state are permanently discarded. The history becomes a
            straight line from that point forward. Save a snapshot before jumping
            if you want to preserve the original chain.
        </div>

        <div class="tip">
            Use <strong>Save Parameters to File</strong> in the History dialog to
            export the complete operation chain with all parameters — useful for
            method documentation and reproducibility reporting.
        </div>

        <h3>Help Button (?)</h3>
        <p>The small <strong>?</strong> button in the Spectra Processing panel opens
        this User Guide. Each operation also has its own Help button inside the
        dialog opened by Run.</p>

        <!-- ═══════════════════════════════════════════════════════════
             5. OPERATIONS
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="operations">5. Processing Operations</h2>

        <!-- Define Spectral Range -->
        <h3 id="data-range">Define Spectral Range <a href="help://data_range" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Restricts the x-axis range and/or applies x-axis linearisation. Use this
        as a first step to bring all spectra onto a common grid before any other
        processing.</p>
        <ul>
            <li><strong>X-Scale Range (X-min / X-max):</strong> crop the spectral range</li>
            <li><strong>Include / Exclude Ranges:</strong> keep or remove specific intervals,
                shown as green (include) or red (exclude) shading on the preview plot</li>
            <li><strong>Apply linearisation:</strong> interpolates each spectrum to a
                uniform x-step — required before Combine Spectra or Spectral Calculator
                when spectra have different x-axes</li>
            <li><strong>X-step:</strong> spacing of the linearised grid</li>
        </ul>
        <div class="tip">Clicking a spectrum in the preview list shows its ranges —
        selection is for viewing convenience only; processing applies to all loaded
        spectra.</div>

        <!-- Normalization -->
        <h3 id="normalization">Normalization <a href="help://normalization" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Scales spectra so that intensity differences due to experimental conditions
        (laser power, integration time, concentration) do not mask real spectral
        differences.</p>
        <h4>Intensity methods</h4>
        <ul>
            <li><strong>Peak intensity (I/I_max):</strong> divide by maximum in region</li>
            <li><strong>Area (integral):</strong> divide by integral over region</li>
            <li><strong>Vector norm (L2):</strong> divide by Euclidean norm</li>
            <li><strong>Robust peak (Nth percentile):</strong> divide by Nth percentile</li>
            <li><strong>Mean of top N%:</strong> divide by mean of top N% of intensities</li>
        </ul>
        <h4>Scatter correction methods</h4>
        <ul>
            <li><strong>SNV:</strong> Standard Normal Variate — mean-centre and scale by std</li>
            <li><strong>MSC:</strong> Multiplicative Scatter Correction</li>
            <li><strong>SVD factor norm:</strong> normalise to first SVD component</li>
        </ul>
        <p>Define one or more <strong>normalization regions</strong> by dragging on the
        preview plot or entering From / To manually. Include or exclude modes
        available.</p>

        <!-- CD Unit Conversion -->
        <h3 id="cd-unit-conversion">CD Unit Conversion <a href="help://cd_unit_conversion" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Converts raw circular dichroism spectra (millidegrees, the typical raw
        output of a CD spectropolarimeter) into molar/mean-residue ellipticity [&theta;],
        differential molar extinction coefficient &Delta;&epsilon;, or differential
        absorbance &Delta;A.</p>
        <ul>
            <li>Path length, concentration, and molecular weight are entered
                <strong>per spectrum</strong> in an Excel-like table (Ctrl+C/X/V,
                paste from an external spreadsheet, paste one value onto many
                selected cells) — real CD batches routinely mix different
                concentrations and path lengths, e.g. a titration series.</li>
            <li>Works directly from a molar concentration (M / mM / &micro;M) — the
                common case for nucleic acids quantified by A260 absorbance — with
                <strong>no molecular weight needed at all</strong>.</li>
            <li>A molecular weight column is only shown if concentration is entered
                as mg/mL instead, purely to convert it to mol/L — the more common
                path for protein samples quantified by mass or A280.</li>
            <li>Mean-residue/mean-nucleotide ellipticity just needs the number of
                residues/nucleotides in the molecule, entered <strong>per
                spectrum</strong> in the same table (a batch can mix molecules
                of different length), not a second weight value.</li>
        </ul>
        <p>See the dedicated <em>CD Unit Conversion Help</em> for the full formulas.</p>

        <!-- X-axis Unit Conversion -->
        <h3 id="xaxis-unit-conversion">X-axis Unit Conversion <a href="help://xaxis_unit_conversion" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Converts a spectrum's x-axis between wavelength (nm), wavenumber
        (cm&#8315;&sup1;), energy (eV), and frequency (Hz) — exact,
        parameter-free physics formulas (no concentration/path length
        involved, unlike CD Unit Conversion). Useful for comparing an
        experimental band position against a computed transition energy
        (e.g. TD-DFT results reported in eV), or overlaying spectra recorded
        on different axis conventions.</p>
        <ul>
            <li>From/To unit are chosen from dropdowns, shared across the
                whole selection — a live preview table shows each spectrum's
                range before and after.</li>
            <li>The converted x-axis is automatically re-sorted ascending
                (an application-wide requirement), since these conversions
                reverse the axis direction.</li>
            <li>Does <strong>not</strong> support Raman shift conversion —
                that needs the excitation laser wavelength plus a reliably
                calibrated wavelength axis, out of scope for this operation.
                See the dedicated help page for why.</li>
        </ul>

        <!-- Mean-Center Spectra (Dataset) -->
        <h3 id="mean-centering">Mean-Center Spectra (Dataset) <a href="help://mean_centering" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Computes the ensemble average spectrum across a selected batch
        (the per-wavelength mean, averaged across every spectrum in the
        selection) and subtracts it from every spectrum in that batch —
        the same centering step the PCA / SVD dialogs perform internally
        when their own "Mean-center" checkbox is on, exposed here as its
        own standalone operation, independent of running any
        decomposition.</p>
        <ul>
            <li>Every selected spectrum must share an identical x-axis —
                same requirement as PCA/SVD, since averaging "the same
                wavelength across spectra" only makes sense if that
                wavelength is actually the same for all of them.</li>
            <li>Optional checkbox also adds the computed average itself as
                a new spectrum, useful as a reference or QC artifact.</li>
            <li><strong>Not</strong> the same as Normalization's "Mean
                Centering" mode, which subtracts each spectrum's own
                scalar mean from itself (independent of the other
                spectra) — this operation subtracts one shared average
                computed from the whole batch. See the dedicated help
                page for the full distinction.</li>
        </ul>

        <!-- Smoothing -->
        <h3 id="smoothing">SG-Smoothing <a href="help://sg_smoothing" style="font-size:8pt; font-weight:normal;">📖 open help</a> (Savitzky-Golay)</h3>
        <p>Reduces noise while preserving peak positions and shapes better than simple
        moving-average smoothing.</p>
        <ul>
            <li><strong>Window size:</strong> number of points (must be odd); larger = more smoothing</li>
            <li><strong>Polynomial order:</strong> degree of fitting polynomial; higher = less smoothing</li>
            <li><strong>Set Individual Delta Values…:</strong> override the derivative spacing
                for specific spectra instead of using the estimated/default value for all of
                them. These overrides persist across selections and dialog reopens, and follow
                a renamed spectrum automatically.</li>
        </ul>
        <div class="tip">For Raman data with fluorescence, use a larger window.
        For well-resolved narrow peaks, use a small window with low polynomial order.</div>

        <h3 id="fft-denoising">FFT Denoising <a href="help://fft_denoising" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Filters spectra in the frequency domain by zeroing selected frequency bands.
        Everything removed lives in one stop-bands table: <strong>Quick cut</strong>
        (Cut low / Cut high) adds a band covering the whole low or high end in one
        click — removing slow baseline drift or high-frequency electronic noise
        respectively — and a manually typed band can target a specific noise spike.</p>
        <div class="tip">Inspect the Power spectrum tab first to see where signal energy is
        concentrated before choosing what to cut.</div>

        <!-- Manual Baseline -->
        <h3 id="baseline">Manual Baseline Correction <a href="help://manual_baseline" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Interactively place anchor points on the spectrum; a spline or polynomial
        is fitted through the points and subtracted.</p>
        <ul>
            <li><strong>Left-click:</strong> add a point</li>
            <li><strong>Right-click:</strong> remove nearest point</li>
            <li><strong>Fit type:</strong> Cubic spline or polynomial</li>
            <li><strong>Polynomial order:</strong> used when fit type is polynomial</li>
            <li><strong>Previous / Next:</strong> navigate between spectra</li>
            <li><strong>Both:</strong> view original and corrected overlaid</li>
        </ul>
        <p>Anchor points are stored per spectrum — each spectrum has its own
        individually placed baseline.</p>

        <!-- Automated Baseline -->
        <h3 id="auto-baseline">Automated Baseline <a href="help://automated_baseline" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Fits a baseline automatically without manual point placement, using
        ALS (Asymmetric Least Squares), airPLS (adaptive iteratively reweighted
        PLS), or arPLS (asymmetrically reweighted PLS) — selectable in the dialog, with one-click "Region Shortcut" presets
        (e.g. water band, for aqueous/biological samples) that add straight into
        the fitting-regions table. Useful for batch processing where manual
        correction would be impractical.</p>

        <!-- SVD Background -->
        <h3 id="svd-background">SVD Background <a href="help://svd_background" style="font-size:8pt; font-weight:normal;">📖 open help</a> Correction</h3>
        <p>Uses Singular Value Decomposition to separate spectral signal from
        background. Particularly effective for broad fluorescence backgrounds in
        Raman spectra.</p>

        <!-- Interactive Subtraction -->
        <h3 id="subtraction">Interactive Subtraction <a href="help://interactive_subtraction" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Subtracts a scaled reference spectrum (subtrahend) from one or more sample
        spectra (minuends) with real-time visual feedback.</p>
        <div class="pipeline">
            <strong>Formula:</strong> Difference(x) = Minuend(x) − Factor × Subtrahend(x)
        </div>
        <ul>
            <li>Select <strong>Minuend</strong> (blue) and <strong>Subtrahend</strong> (red) from the right-hand lists</li>
            <li>Adjust the <strong>slider</strong> — the difference spectrum (green) updates live</li>
            <li><strong>Center / Half-width</strong> control the slider range; click
                <strong>Set as center</strong> to recentre without losing the current factor</li>
            <li><strong>Update</strong> stores the factor for the current minuend/subtrahend pair —
                each minuend keeps only one stored subtrahend at a time, so storing a new one
                replaces rather than adds to it</li>
            <li><strong>Selected mode:</strong> apply the same factor to multiple minuends at once</li>
            <li><strong>Apply</strong> / <strong>Add as New</strong> commit every stored factor
                directly from this dialog — there's no separate Run step in the main window</li>
            <li>Stored factors survive closing and reopening the dialog for the same spectra,
                and follow a renamed spectrum automatically</li>
            <li><strong>Show info</strong> lists everything currently stored and is also where
                you remove entries — select row(s) and click <strong>Remove Selected</strong>,
                or <strong>Select All</strong> first to clear everything</li>
        </ul>
        <p>See the dedicated <em>Interactive Subtraction Help</em> for full details.</p>

        <!-- X-Axis Alignment -->
        <h3 id="xaxis">X-Axis Alignment <a href="help://xaxis_alignment" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Corrects systematic shifts of the x-axis (wavenumber or wavelength) between
        spectra that are otherwise the same shape — e.g. drift between measurement
        sessions or instruments.</p>
        <ul>
            <li>Pick a <strong>Reference</strong> spectrum; every other selected spectrum
                is shifted to best match it, then resampled onto its x-grid</li>
            <li><strong>Max shift</strong> bounds how far the optimiser searches;
                <strong>Run preview</strong> shows the resulting shift table and plot
                before anything is committed</li>
            <li><strong>Apply</strong> / <strong>Add as New</strong> commit directly from
                the dialog, same as Interactive Subtraction — no separate Run step</li>
        </ul>
        <p>A ready-made test dataset (32 spectra, each shifted by a known amount) is
        available under <b>Help &rarr; Test datasets &rarr; Synthetic &rarr; X-Axis
        Alignment</b>.</p>
        <p>See the dedicated <em>X-Axis Alignment Help</em> for full details.</p>

        <!-- SVD Interpolation -->
        <h3 id="svd-interpolation">SVD Interpolation <a href="help://svd_interpolation" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Generates <strong>new, artificial spectra</strong> at parameter values you never
        actually measured — e.g. spectra measured at temperatures 5&deg;C to 90&deg;C in
        5&deg; steps can be used to synthesize a spectrum at 22&deg;C, without measuring it.</p>
        <ul>
            <li>Decomposes the selected spectra via SVD, then lets you sketch how each
                component's coefficient varies with a parameter (temperature, pH, time, &hellip;)
                by placing points on a plot and fitting a <strong>polynomial or spline</strong>
                through them — same click-to-edit interaction as Manual Baseline</li>
            <li>Whichever components end up with a fitted curve are used in the reconstruction;
                there's no separate step for marking components as "relevant"</li>
            <li><strong>Guess # of components</strong> opens a small diagnostic plot (variance,
                singular values, or residual error) to help judge how many components are
                worth bothering with</li>
            <li>Enter target parameter values (typed, or a start/end/step range), then
                <strong>Compute Preview</strong> to see the result before committing — nothing
                is added to the main list until you click <strong>Apply</strong> (replaces the
                source spectra with the interpolated ones) or <strong>Add as New</strong>
                (keeps the sources, adds the interpolated spectra alongside them)</li>
            <li>Requires every selected spectrum to already share one x-axis, same as SVD
                Analysis, PCA, MCR-ALS and NMF</li>
        </ul>
        <p>See the dedicated <em>SVD Interpolation Help</em> for full details.</p>

        <!-- Combine Spectra -->
        <h3 id="combine">Combine Spectra <a href="help://combine_spectra" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Creates a single new spectrum from multiple selected spectra by averaging
        or summing their y-values point-by-point.</p>
        <ul>
            <li><strong>Average:</strong> mean y-value at each x — standard technique for
                improving signal-to-noise ratio from replicate measurements</li>
            <li><strong>Sum:</strong> total y-value at each x</li>
            <li><strong>Output name:</strong> label for the new spectrum</li>
            <li><strong>Apply:</strong> replaces the source spectra with the combined result</li>
            <li><strong>Add as New:</strong> keeps the source spectra untouched and adds the
                combined result under the chosen output name</li>
        </ul>
        <div class="warning">
            All selected spectra must have <strong>identical x-axes</strong>. Use
            Define Spectral Range → Apply linearisation first if they differ.
        </div>

        <!-- Spectral Calculator -->
        <h3 id="calculator">Spectral Calculator <a href="help://spectral_calculator" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Evaluates a user-defined mathematical formula to create a new spectrum.
        Spectrum labels are used directly as variable names in the formula.</p>
        <div class="pipeline">
            <strong>Examples:</strong><br>
            2*sp1 + 0.5*sp2 − sp3 &nbsp;&nbsp; (linear combination)<br>
            sp1 / sp2 &nbsp;&nbsp; (ratio spectrum)<br>
            (sp1 − sp2) / (sp1 + sp2) &nbsp;&nbsp; (normalised difference)<br>
            absorbance(sp1) &nbsp;&nbsp; (−log₁₀(T))<br>
            derivative(snv(sp1)) &nbsp;&nbsp; (SNV then first derivative)
        </div>
        <p>Available built-in functions: <em>abs, sqrt, log, log10, exp, sin, cos,
        mean, sum, min, max, cumsum, absorbance, transmittance, kubelka_munk,
        derivative, second_deriv, normalise, snv.</em></p>
        <ul>
            <li>Click spectrum labels or function names in the right-hand panel to
                insert them at the cursor</li>
            <li>Click <strong>Validate formula</strong> before Apply / Add as New to catch errors early</li>
            <li>All spectra must share an identical x-axis (use Define Spectral Range
                → Apply linearisation first)</li>
        </ul>
        <p>See the dedicated <em>Spectral Calculator Help</em> for a full function
        reference and examples.</p>

        <!-- Spike Removal -->
        <h3 id="spike">Spike Removal <a href="help://spike_removal" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Detects cosmic ray spikes automatically (modified Z-score on the 2nd derivative),
        then lets you review and edit the detections interactively — reject false positives,
        add missed spikes manually — before committing the removal.</p>

        <!-- Peak Fitting -->
        <h3 id="peak-fitting">Peak Fitting <a href="help://peak_fitting" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>Fits Gaussian, Lorentzian, Voigt, or pseudo-Voigt peak models to selected
        regions of a spectrum. Provides peak positions, widths, areas, and fit
        quality metrics.</p>
        <div class="warning">
            Peak Fitting operates on <strong>exactly one</strong> spectrum at a time.
        </div>

        <h3 id="cosmic-ray">Cosmic Ray Detection (Cross-spectrum) <a href="help://cosmic_ray" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Compares each spectrum against the group at every x-position using a modified
        Z-score. Points that are statistical outliers relative to the group median are
        flagged and replaced with the group median value.</p>
        <div class="warning"><strong>Only use on replicate spectra</strong> (repeated
        measurements of the same or similar samples). Genuine spectral differences between
        different samples will be incorrectly flagged as cosmic rays. Reliable with
        &ge;30 spectra; for fewer spectra use the single-spectrum Spike Removal instead.
        </div>
        <ul>
            <li><strong>Threshold (Z-score):</strong> lower = more sensitive (default 10).
                Inspect the heatmap to confirm flagged points are real rays before applying.</li>
            <li><strong>Outlier heatmap:</strong> shows |Z-score| at every
                (spectrum, x-position) — bright streaks in one spectrum = cosmic ray.</li>
            <li><strong>Summary &amp; Preview:</strong> table of flagged points per
                spectrum and a live spectrum preview side by side — click a row to see
                that spectrum with flagged points marked in red.</li>
        </ul>

        <h3 id="resolution">Resolution Enhancement (Wiener Deconvolution) <a href="help://resolution" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Mathematically reverses the broadening introduced by the instrument response
        function (IRF), recovering sharper spectral features.</p>
        <ul>
            <li><strong>IRF width (&sigma;):</strong> Gaussian half-width in x-axis units.
                Estimate from a known sharp peak: &sigma; = FWHM / 2.355.
                Typical values: 0.5&ndash;2&nbsp;cm&sup1; (high-res Raman),
                2&ndash;5&nbsp;cm&sup1; (standard Raman), 4&ndash;16&nbsp;cm&sup1; (FTIR).</li>
            <li><strong>SNR:</strong> higher = more aggressive sharpening but more noise
                amplification. Start at 100 and reduce if ringing artefacts appear.</li>
            <li>Pre-process first: baseline correction then light smoothing before enhancement.</li>
        </ul>

        <h3 id="batch-pipeline">Batch Pipeline Replay <a href="help://batch_pipeline" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Captures a named, reusable sequence of the operations above (with their
        exact settings) from Operations History, so it can be run again later on any
        spectra selection — in this session or a future one — with a single click,
        instead of manually repeating a multi-step recipe every time.</p>
        <ul>
            <li><strong>Save:</strong> Operations History &rarr; <em>Save as
                Pipeline...</em> — check which committed operations to include, name
                the pipeline, Save.</li>
            <li><strong>Run:</strong> select spectra, then Operations &rarr;
                Batch Pipeline &rarr; <em>Run Pipeline...</em> — pick a saved
                pipeline, Apply or Add as New.</li>
            <li>Not every operation can be captured — see the help page for the full
                list of what's eligible and why some (Manual baseline, CD Unit
                Conversion, and other multi-spectrum operations) aren't.</li>
        </ul>

        <!-- ═══════════════════════════════════════════════════════════
             6. SPECTRA ANALYSIS & VISUALIZATION
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="visualisation-analysis">6. Spectra Analysis &amp; Visualization</h2>

        <div class="info">
            <strong>These tools generally don't appear in Operations History.</strong>
            Unlike the Processing Operations in section 5, the tools below compute and
            display a derived result without changing any spectrum's actual data — there's
            nothing for "jump to a previous state" to undo, so running them isn't recorded
            as a step. The exceptions, all only when they actually add new spectra to your
            list: <a href="#peak-fitting">Peak Fitting</a>'s Output Options (only the
            branch that creates a fit/residual/individual-peak spectrum is recorded — fitting
            without checking any of those boxes is not), <a href="#melting-curve">Melting
            Curve Analysis</a>'s Output Options (same rule — only recorded when an output
            option actually creates a spectrum), <a href="#2d-map">2D Spectral Map</a>'s
            ROI export, and <a href="#nmf">NMF</a>'s <strong>Export Components&hellip;</strong>
            and <a href="#mcr-als">MCR-ALS</a>'s <strong>Export Pure Spectra&hellip;</strong>
            (recorded the moment you confirm the export, regardless of which tab —
            Components/Pure Spectra, Concentrations, Reconstruction, or Fit Quality — you
            were viewing when you opened it, since the export itself is one step). Band
            Ratio still saves its result into each
            spectrum's own metadata (visible via right-click → Show Metadata) even though
            it isn't a history step.
        </div>

        <div class="info">
            <strong>Export PDF Report:</strong> PLS/PLS-DA, Kinetics Fitting,
            QC/Outlier Detection, Isosbestic Point Detection, Band Ratio, and
            Reference Library Matching each have an <strong>Export PDF&hellip;</strong>
            button next to Export CSV, producing a self-contained PDF with a title
            page (what was run, when, on which spectra, with which settings), the
            current plot, and the full results table &mdash; handy for records or
            sharing a result without reopening the app. Melting Curve Analysis has
            the same report under its <strong>Fit Details &rarr; Export PDF
            Report&hellip;</strong> menu instead, since its output is organized
            around a single fit rather than a results table.
        </div>

        <h3 id="svd-analysis">SVD Analysis <a href="help://svd_analysis" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Decomposes the spectral dataset into orthogonal components via Singular
        Value Decomposition. Useful for identifying the number of independent
        chemical components, noise estimation, and dimensionality reduction.</p>
        <ul>
            <li><strong>View SVD Components:</strong> step through components
                (subspectra) one at a time or jump directly; tick several to
                display together; <strong>Invert</strong> flips a component's
                arbitrary sign without changing what it represents.</li>
            <li><strong>Diagnostics</strong> (its own tab): seven metrics — singular values,
                eigenvalue, explained/cumulative variance, residual error, and Malinowski's
                IND function — to help decide how many components are real
                signal versus noise.</li>
            <li><strong>Reconstruction:</strong> rebuild spectra from All
                components (sanity check), the First N (noise reduction), or
                Only corrected components (baseline + noise removal in one
                step, by correcting just the dominant subspectra).</li>
            <li><strong>Coefficient X-axis:</strong> coefficient (V) plots default to
                plain spectrum order (1, 2, 3, ...); switch to <strong>Parameter
                values</strong> to instead plot against a physical quantity that
                varies across your spectra — temperature, pH, time, etc. — one value
                per spectrum, loaded from a text file (drag &amp; drop works too),
                entered in a spreadsheet-style table with Excel-style fill-series and
                copy/cut/paste, or typed manually; or switch to <strong>Spectrum
                labels</strong> to show each spectrum's name instead of a number, in the
                same order the spectra appear in the main window's list (honoring this
                dialog's own Shorten names checkbox). Use the "?" button next to those
                radio buttons for details. Parameter values are cleared on every
                recompute.</li>
            <li><strong>Save:</strong> export subspectra, coefficients, and
                diagnostics to Excel or text/CSV.</li>
        </ul>
        <div class="tip"><strong>SVD Analysis vs. PCA Scores &amp; Loadings:</strong>
        both use the same underlying decomposition, for different questions. Use
        <strong>this dialog</strong> for component-by-component inspection ("what does
        component 3 look like, and how strongly does it appear across my samples?") and
        reconstruction. Use <strong><a href="#pca-scores">PCA Scores &amp;
        Loadings</a></strong> below for sample- and variable-level questions ("do my
        spectra cluster?", "which wavenumbers drive that separation?") — including 3D
        score plots and Hotelling's T&sup2; outlier detection.</div>

        <h3 id="pca-scores">PCA Scores &amp; Loadings <a href="help://pca_scores" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Visualises SVD results as PCA-style scores and loadings plots.</p>
        <ul>
            <li><strong>Scores tab:</strong> scatter plot of PC<sub>x</sub> vs
                PC<sub>y</sub> — one point per spectrum. Colour by index (drift over
                time) or by a third component score. Spectra that are similar cluster
                together; outliers appear isolated.</li>
            <li><strong>Loadings tab:</strong> spectral profiles of each component,
                showing which wavenumber regions drive that component. Offset for
                readability.</li>
            <li><strong>Variance tab:</strong> seven metrics (same set as SVD Analysis's
                Diagnostics), with Single/Compare/Overview view modes. The elbow in the
                cumulative curve, or the minimum of Malinowski IND, indicates the optimal
                number of components.</li>
        </ul>
        <div class="tip">Pre-process spectra (baseline correction + normalisation)
        before PCA. Without baseline correction, PC1 will be dominated by the
        fluorescence background. For component-by-component inspection and
        reconstruction instead of sample/variable-level questions, see
        <a href="#svd-analysis">SVD Analysis</a> above. Reopening this dialog for the
        same spectra selection restores your last-used component count, axis choices,
        2D/3D view, and colour-by setting; selecting a different set of spectra resets
        to the defaults instead.</div>

        <h3 id="nmf">NMF (Non-negative Matrix Factorisation) <a href="help://nmf" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Decomposes spectra into non-negative spectral components (H) and abundance
        scores (W). Unlike PCA, components are always non-negative so they physically
        resemble real spectra and abundances resemble concentrations &mdash; directly
        interpretable for mixture analysis.</p>
        <ul>
            <li><strong>Components tab:</strong> spectral profiles of each NMF component.</li>
            <li><strong>Concentrations tab:</strong> abundance of each component per
                spectrum, as lines (default), bars, or an exact
                <strong>table</strong> of the numbers. "Normalize to 100% per spectrum"
                turns them into readable percentages.</li>
            <li><strong>Reconstruction tab:</strong> original vs reconstructed spectrum,
                with per-component contributions stacked as coloured fills that add up to
                the reconstruction. A checkbox hides the fills for a clean overlay.</li>
            <li><strong>Fit Quality tab:</strong> three views &mdash; <em>Per spectrum</em>
                (which spectra fit worst), <em>Elbow</em> (lack-of-fit vs number of
                components, to choose that number), and <em>Median residual vs component
                count</em>. "Restarts per component count" controls how hard the two
                sweeps try.</li>
            <li><strong>Reference spectra (optional):</strong> anchor a component to a
                <em>known</em> pure spectrum you already have. This is the most effective
                way to escape the non-uniqueness problem below &mdash; see the warning.</li>
            <li><strong>Export:</strong> H (components) and W (scores) to Excel or CSV.</li>
        </ul>
        <div class="warning"><strong>NMF requires non-negative data.</strong> Negative
        values are clipped to zero, which destroys real negative bands. <strong>Not
        suitable for CD, ROA or VCD spectra</strong>, or spectra with uncorrected negative
        baselines &mdash; for genuinely signed data use MCR-ALS with spectral
        non-negativity switched <em>off</em>. Recommended pipeline: Data range &rarr;
        Baseline correction &rarr; Normalisation &rarr; NMF.</div>

        <h3 id="mcr-als">MCR-ALS (Multivariate Curve Resolution) <a href="help://mcr_als" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Decomposes spectra into pure component spectra (ST) and concentration
        profiles (C), found by alternating constrained least-squares fits rather than
        NMF's multiplicative-update algorithm &mdash; the practical difference is that
        MCR-ALS lets you turn non-negativity for the spectra and for the concentrations
        on or off independently, where NMF requires both to be non-negative.</p>
        <ul>
            <li><strong>Pure Spectra tab:</strong> the resolved component spectra, offset for clarity.</li>
            <li><strong>Concentrations tab:</strong> each component's concentration per
                spectrum, as lines (default), bars, or an exact <strong>table</strong>.
                "Normalize to 100% per spectrum" turns them into readable percentages.</li>
            <li><strong>Reconstruction tab:</strong> original vs reconstructed spectrum,
                with per-component contributions stacked as coloured fills that add up to
                the reconstruction. A checkbox hides the fills for a clean overlay.</li>
            <li><strong>Fit Quality tab:</strong> three views &mdash; <em>Per spectrum</em>,
                <em>Elbow</em> (lack-of-fit vs number of components), and <em>Median
                residual vs component count</em>.</li>
            <li><strong>Constraints:</strong> non-negativity for the spectra and for the
                concentrations, independently &mdash; and <strong>Closure</strong>
                (concentrations sum to 100% per spectrum), which is correct only for a
                genuinely <em>closed</em> system where total material is conserved (DNA
                melting, protein folding). Applying closure when it isn't true can make
                the correct answer unreachable, so it is off by default.</li>
            <li><strong>Reference spectra (optional):</strong> anchor a component to a
                <em>known</em> pure spectrum. The most effective cure for the
                non-uniqueness problem below &mdash; see the warning.</li>
            <li><strong>Export:</strong> ST (pure spectra) and C (concentrations) to Excel or CSV.</li>
        </ul>
        <div class="warning"><strong>A good fit does not mean a correct answer.</strong>
        This is the single most important thing to understand about both MCR-ALS and NMF.
        Many different decompositions can reproduce your data equally well (&ldquo;rotational
        ambiguity&rdquo;), so a low lack-of-fit proves only that the model reproduces the
        numbers &mdash; not that the components are chemically real. On the built-in signed
        test datasets (ROA), a fit with a near-perfect <em>0.05% lack-of-fit</em> recovered
        the true components only about <em>half</em> correctly.
        <br><br>
        Two defences: use <strong>&ldquo;Run N times, keep best&rdquo;</strong> and check the
        consensus figure it reports (do the good runs agree on the component <em>shapes</em>,
        not just the score?); and wherever you have a known pure spectrum, anchor it with
        <strong>Reference spectra</strong> &mdash; on those same ROA datasets this lifts
        recovery from ~0.5 to ~0.99. Treat any single blind result as a candidate to check
        against chemical knowledge, never as a definitive answer.</div>

        <h3 id="reference-matching">Reference Library Matching <a href="help://reference_matching" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Matches each query spectrum against a reference library using cosine,
        Pearson, or Euclidean similarity. The library can be built from loaded spectra
        or loaded from external files.</p>
        <ul>
            <li><strong>X-axis overlap detection:</strong> matches below the minimum
                overlap threshold are flagged as unreliable (grey rows, red overlap %).</li>
            <li><strong>Results tab:</strong> ranked matches per query spectrum with
                score and overlap %.</li>
            <li><strong>Plots tab:</strong> bar chart of scores per query spectrum
                across all references. Grey bars = references not in top-N for that query.</li>
        </ul>
        <p>Results table: Copy to clipboard, Export CSV, or Export PDF (see the
        Export PDF Report note above).</p>
        <div class="warning">Pre-process query and reference spectra identically
        (same baseline correction, range, normalisation) before matching. Raw spectra
        with large fluorescence backgrounds produce misleadingly high scores.</div>

        <h3 id="band-ratio">Band Ratio / Peak Area Calculator <a href="help://band_ratio" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Computes ratios, sums, differences, and intensity values over user-defined
        spectral ranges. Six metrics available: baseline-corrected integral, integral,
        mean, peak intensity, peak position, and intensity at x. Results displayed as
        bar, line, or scatter plots per spectrum. Copy to clipboard, Export CSV, or
        Export PDF (see the Export PDF Report note above) from the results table.</p>

        <h3 id="melting-curve">Melting Curve Analysis <a href="help://melting_curve" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Builds a thermal melting curve from a series of spectra recorded at
        different temperatures &mdash; select two or more spectra, and this tool
        reads one signal value from each (at a chosen x-position, e.g. a
        wavenumber) to plot against temperature. From there it offers interactive
        (slider- or plot-driven) linear-baseline normalization, an Arrhenius-based
        two-state estimate of deltaH/deltaS/Tm, and a multi-sigmoid (up to 4
        components) fit for resolving multiphasic transitions &mdash; each
        component getting its own isolated curve and its own Arrhenius plot.
        Fit results can be copied or saved as a text report, exported as a PDF
        report (plot, settings, and the fit-results table &mdash; via
        <strong>Fit Details &rarr; Export PDF Report&hellip;</strong>), or kept in a
        Saved Fits list (persists across reopening the dialog) to compare
        several results side by side. Like Peak Fitting,
        nothing is saved unless at least one Output Option is checked; each new
        spectrum this creates (extracted curve, normalized curve, baselines, fit,
        residual, individual components) carries the source spectra and fit
        parameters in its own metadata. Six ready-made test datasets (1&ndash;3
        known thermal transitions, clean/noisy) are available under
        <b>Help &rarr; Test datasets &rarr; Synthetic &rarr; Melting curve</b>.</p>

        <h3 id="isosbestic-point">Isosbestic / Isodichroic Point Detection <a href="help://isosbestic_point" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Finds the x-axis location(s) where a series of spectra (a titration,
        temperature ramp, pH series, or time course) all cross through the
        same y-value &mdash; the classic signature of a clean two-species
        interconversion. Works by finding a distinctive local minimum in the
        cross-spectrum standard deviation, filtered by a configurable
        prominence threshold to reject noise-driven wiggles. Read-only
        analysis (like Band Ratio and Reference Matching): no spectra are
        added or modified, nothing is written to Operations History &mdash;
        results are shown in a table (x-location, mean y, std, prominence,
        relative tightness) with Copy/Export CSV/Export PDF (see the Export
        PDF Report note above). Requires all selected
        spectra to share one identical x-axis (use Data Range with
        linearisation first if they don't), and at least 3 spectra for a
        statistically meaningful result.</p>

        <h3 id="cluster">Cluster Analysis <a href="help://cluster_analysis" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Groups spectra by spectral similarity. Supports k-means and hierarchical
        clustering. Results displayed as dendrograms and colour-coded spectrum lists.</p>

        <h3 id="2d-map">2D Spectral Map <a href="help://map2d" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        
        <p>Visualises spatially-resolved spectra as a false-colour 2D map. Colour
        can represent any band metric, an SVD/PCA/NMF/MCR-ALS component, or a
        cluster label &mdash; PCA here is mean-centered SVD, computed independently
        of the standalone <a href="#pca-scores">PCA Scores &amp; Loadings</a> tool.
        Requires selecting exactly Rows &times; Cols spectra (laid out
        row-by-row) &mdash; a MAT/WITec map import already carries its own
        dimensions and fills these in automatically.</p>

        <h3 id="2d-correlation">2D Correlation (2D-COS) <a href="help://two_d_correlation" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Two-dimensional correlation spectroscopy (Noda's generalized 2D
        correlation method): transforms a stacked set of spectra recorded
        under a varying external perturbation (time, temperature,
        concentration, &hellip;) into a <strong>synchronous</strong> map
        (bands that change in phase) and an <strong>asynchronous</strong> map
        (bands that change out of phase) &mdash; useful for resolving
        overlapping bands that a 1D spectrum can't separate. Requires at
        least 3 spectra, selected/ordered by their real perturbation
        sequence, sharing an identical x-axis. A <strong>Dynamic spectra</strong>
        tab shows the mean/reference-subtracted spectra the maps are computed
        from, for a quick sanity check.</p>

        <h3 id="pls">PLS / PLS-DA <a href="help://pls" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Builds a calibration model from a set of spectra with a known
        property (concentration for <strong>PLS Regression</strong>, class
        label for <strong>PLS-DA</strong> classification), then applies it
        to predict that property for new, unlabeled spectra.</p>
        <ul>
            <li>Select both your calibration standards AND any unknowns you
                want predicted, then open PLS / PLS-DA. Enter each
                calibration spectrum's known value in the table; leave a
                row blank for anything you want treated as an unknown.</li>
            <li>Number of components is auto-selected via cross-validation
                by default (the simplest model within a small tolerance of
                the best cross-validated score, not necessarily the bare
                statistical minimum).</li>
            <li>Diagnostics via the View dropdown: cross-validation curve,
                scores plot, actual-vs-predicted / confusion matrix, and
                regression coefficients + VIP scores by wavelength.</li>
            <li>Calibration/prediction table: Copy to clipboard, Export CSV, or
                Export PDF (see the Export PDF Report note above).</li>
        </ul>

        <h3 id="kinetics-fitting">Kinetics Fitting <a href="help://kinetics_fitting" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Fits exponential kinetic models (decay or rise) to a time series
        of spectra &mdash; select 4 or more spectra recorded at different
        times, and this tool recovers the underlying rate constant(s). Two
        modes are available:</p>
        <ul>
            <li><strong>Single wavelength</strong>: extracts one signal
                value per spectrum (at a chosen x-position, with an
                optional averaging window) and fits it to a sum of up to
                4 exponentials plus an offset &mdash; the classic
                single-trace kinetics fit.</li>
            <li><strong>Global analysis</strong>: fits every wavelength at
                once, assuming all of them share the same 1&ndash;4 rate
                constants (via variable projection: only the rate constants
                are nonlinear, every wavelength's amplitude is solved
                linearly). Recovers each component's own
                Decay-Associated Spectrum (DAS) &mdash; useful when no
                single wavelength cleanly isolates one process.</li>
        </ul>
        <p>Time values are auto-guessed from each spectrum's label (the
        last number found in it) and shown in an editable table &mdash;
        correct any that are wrong before fitting. Components are always
        listed slowest (smallest rate constant) first, fastest last.
        Results (rate constant, tau = 1/k, amplitude, and their
        uncertainties) can be copied, exported as CSV, or exported as a PDF
        report (see the Export PDF Report note above). Two ready-made
        test datasets (single-exponential decay, two-component global
        analysis) are available under
        <b>Help &rarr; Test datasets &rarr; Synthetic &rarr; Kinetics</b>.</p>

        <h3 id="qc-outlier">QC / Outlier Detection <a href="help://qc_outlier" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>

        <p>Checks a batch of spectra (5 or more) against EACH OTHER and
        flags any that don't look like they belong &mdash; a bad
        acquisition, a contaminated or mislabeled sample, an instrument
        glitch. Fits a PCA model to the batch, then scores every spectrum
        on two independent diagnostics: Hotelling T&sup2; (unusual but
        still model-shaped &mdash; e.g. an atypically strong/weak but
        real member) and Q-residual/SPE (doesn't fit the model's spectral
        shape at all &mdash; e.g. a spike or artifact).</p>
        <ul>
            <li>Component count is auto-selected by cumulative explained
                variance (default 95%), or set it yourself.</li>
            <li>Results table is sorted worst-first, with the exceeded
                diagnostic(s) named per spectrum.</li>
            <li>Diagnostics via the View dropdown: distance plot (T&sup2;
                vs Q, the classic "distance-distance" plot), PCA scores,
                and a residual-spectrum view for whichever spectrum is
                selected in the results table &mdash; the most direct way
                to see WHY a flagged spectrum was flagged.</li>
            <li>Results table: Copy to clipboard, Export CSV, or Export PDF
                (see the Export PDF Report note above).</li>
        </ul>
        <p>A ready-made test dataset (30 normal spectra plus 3
        deliberately planted problem spectra) is available under
        <b>Help &rarr; Test datasets &rarr; Synthetic &rarr; QC</b>.</p>

        <p>A ready-made test dataset is also available for
        <a href="#xaxis">X-Axis Alignment</a> (a Spectra Processing operation,
        not an Analysis &amp; Visualization tool, so it isn't covered in this
        section) &mdash; 32 spectra sharing the same bands, each shifted by a
        different known amount along x. Open it under <b>Help &rarr; Test
        datasets &rarr; Synthetic &rarr; X-Axis Alignment</b>.</p>

        <!-- ═══════════════════════════════════════════════════════════
             7. LEGEND
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="legend">7. Legend</h2>
        <p>Open via the <strong>☰ Legend</strong> button below the spectrum list, or
        via right-click on the plot → Legend.</p>

        <div class="screenshot">
            <img src="$LEGEND_DIALOG" width="$LEGEND_DIALOG_W" height="$LEGEND_DIALOG_H" alt="Legend Properties dialog with position, font, and item-limit settings" />
            <p class="caption">The Legend Properties dialog.</p>
        </div>

        <table>
            <tr><th>Setting</th><th>Description</th></tr>
            <tr><td>Show Legend</td><td>Enable/disable the legend entirely</td></tr>
            <tr><td>Position</td><td>Upper right, lower left, centre, etc.</td></tr>
            <tr><td>Movable Legend</td><td>Allow dragging the legend on the plot</td></tr>
            <tr><td>Font / Font Size</td><td>Legend text appearance</td></tr>
            <tr><td>Show All Items</td><td>When unchecked, limit to Maximum Items</td></tr>
            <tr><td>Maximum Items</td><td>Cap number of entries shown</td></tr>
            <tr><td>Number of Columns</td><td>Multi-column layout for compact display</td></tr>
        </table>
        <p>Legend is <strong>off by default</strong>. Enable it deliberately when you
        need to identify individual spectra. Key rule: always enable for Grid plot
        (panels are otherwise unlabelled); keep disabled for large overlay/waterfall
        datasets (&gt;50 spectra) where it slows rendering and adds no readable
        information.</p>
        <p>See the <a href="help://plot_controls">Interactive Update &amp; Legend
        Performance Guide</a> for a full decision table by dataset size and plot type.</p>

        <!-- ═══════════════════════════════════════════════════════════
             8. SAVING & EXPORT
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="save-export">8. Saving &amp; Export</h2>

        <h3>Save Spectra <a href="help://save" style="font-size:8pt; font-weight:normal;">📖 open help</a></h3>
        <p>File → Save spectra exports processed spectra to text/CSV/Excel files, or
        to GRAMS (.spc) — the same binary Thermo/GRAMS format this app can also
        import. Choose which spectra to export and the output format.</p>

        <div class="screenshot">
            <img src="$SAVE_DIALOG" width="$SAVE_DIALOG_W" height="$SAVE_DIALOG_H" alt="Save Options dialog with File Format, Save Mode, X-scale, Layout, and Options groups" />
            <p class="caption">The Save Options dialog: File Format (Text / Excel / GRAMS (.spc) / Snapshot), Save Mode, X-scale, Layout, and formatting Options.</p>
        </div>
        <div class="info">
            <strong>GRAMS (.spc)</strong> requires every spectrum in a Table-mode
            save to share one common x-scale — not optional for this format, since
            a single <code>.spc</code> file's subfiles are structurally tied to one
            shared axis. Save Individual Files has no such restriction. See
            <a href="help://save">Save Spectra help</a> for the full explanation.
        </div>

        <p>When <strong>Use common x-scale</strong> is checked, a <strong>Layout</strong>
        option appears letting you choose <strong>Columns</strong> (the default — spectra
        as columns) or <strong>Rows</strong> (spectra as rows, sharing the x-scale in the
        header row). A small <strong>?</strong> button next to Layout explains why it's
        only offered in that combination. Files saved with Rows layout re-import directly
        by selecting <strong>Row-oriented</strong> in the Import dialog's Layout option —
        no other setting needed.</p>

        <h3>Snapshots</h3>
        <p>Snapshots save the complete application state (all spectra, all processing
        parameters, selections). Use them as checkpoints:</p>
        <ul>
            <li><strong>Save snapshot:</strong> File → Save snapshot</li>
            <li><strong>Load snapshot:</strong> File → Load snapshot</li>
            <li>Snapshots support undo — reload an earlier snapshot to reverse
                operations</li>
        </ul>

        <h3>Plot Export</h3>
        <p>Use the Save icon in the matplotlib toolbar to export the current plot.
        For publication-quality output, use <strong>Open in new window</strong>
        (right-click on plot) which gives a full matplotlib window with all export
        options (PNG, PDF, SVG, EPS).</p>

        <h3>Operations History Export</h3>
        <p>The History dialog shows all applied operations with full parameters and
        can be exported for method documentation.</p>

        <!-- ═══════════════════════════════════════════════════════════
             9. KEYBOARD SHORTCUTS
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="keyboard">9. Keyboard Shortcuts</h2>
        <table>
            <tr><th>Shortcut</th><th>Action</th></tr>
            <tr><td><span class="kbd">Ctrl+A</span></td><td>Select all spectra</td></tr>
            <tr><td><span class="kbd">Ctrl+U</span></td><td>Deselect all spectra</td></tr>
            <tr><td><span class="kbd">Shift+click</span></td><td>Select contiguous range from last-clicked item to target (Excel-style)</td></tr>
            <tr><td><span class="kbd">Ctrl+click</span></td><td>Toggle individual spectrum in / out of selection</td></tr>
        </table>

        <!-- ═══════════════════════════════════════════════════════════
             10. SPECTROSCOPY GUIDELINES
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="spectroscopy">10. Spectroscopy-Specific Guidelines</h2>

        <h3>Recommended Processing Order</h3>
        <div class="pipeline">
            Define Spectral Range &rarr; Cosmic Ray Detection (for replicate series)
            &rarr; Spike Removal &rarr; Baseline Correction &rarr; Smoothing
            &rarr; Normalisation &rarr; Further analysis
            (PCA / NMF / Reference Matching / Band Ratio)
        </div>

        <h3>IR / FTIR</h3>
        <div class="info"><ul>
            <li>Focus on functional group regions (600–4000 cm⁻¹)</li>
            <li>Baseline correction essential for quantitative analysis</li>
            <li>Use peak normalization for comparison studies</li>
            <li>Overlay plots useful for library matching</li>
        </ul></div>

        <h3>Raman</h3>
        <div class="info"><ul>
            <li>Remove laser line and edge filter region (typically 0–100 cm⁻¹) using Data Range</li>
            <li>Use SVD Background or automated baseline for fluorescence removal</li>
            <li>Use Spike Removal for cosmic rays</li>
            <li>Normalise to account for laser power and integration time variations</li>
        </ul></div>

        <h3>UV-Vis</h3>
        <div class="info"><ul>
            <li>Subtract solvent/buffer background using Interactive Subtraction</li>
            <li>Use absorbance() in Spectral Calculator for T→A conversion</li>
            <li>Normalise at absorption maxima or by concentration</li>
        </ul></div>

        <h3>NIR</h3>
        <div class="info"><ul>
            <li>Apply SNV or MSC normalisation for scatter correction</li>
            <li>SG first or second derivative for baseline removal and band resolution</li>
            <li>Use derivative(snv(sp)) in Spectral Calculator for standard NIR preprocessing</li>
        </ul></div>

        <h3>NMR</h3>
        <div class="info"><ul>
            <li>Select chemical shift regions of interest with Data Range</li>
            <li>Use peak detection for integration region definition</li>
            <li>Internal standard normalisation via Normalization</li>
        </ul></div>

        <!-- ═══════════════════════════════════════════════════════════
             11. TROUBLESHOOTING
             ═══════════════════════════════════════════════════════════ -->
        <h2 id="test-datasets">11. Test Datasets (known ground truth)</h2>

        <p>The application ships with <strong>22 synthetic datasets</strong> whose
        true pure components and true concentrations are known exactly. Open them from
        <strong>Help &rarr; Test datasets &rarr; Synthetic</strong>; the same menu has
        <em>Open datasets folder&hellip;</em> to reach the files themselves.</p>

        <p>They exist to answer the one question real data cannot: <em>is my
        decomposition actually right, not merely well-fitting?</em> Every workbook holds
        the mixture spectra on a <code>Spectra</code> sheet (the one you import) plus
        <code>Pure_components</code>, <code>Concentrations</code>,
        <code>Ground_truth</code> and <code>Info</code> sheets holding the answers.</p>

        <table>
            <tr><th>Family</th><th>Character</th><th>Settings to use</th></tr>
            <tr><td>Raman (6 files)</td><td>Many sharp bands, varied heights and widths;
                all positive</td><td>MCR-ALS with both non-negativity constraints, or NMF</td></tr>
            <tr><td>UV/Vis (4 files)</td><td>Only a few, very broad bands; all positive</td>
                <td>Same; NMF performs especially well here</td></tr>
            <tr><td>CD (4 files)</td><td>Broad electronic bands, genuinely <strong>signed</strong></td>
                <td>MCR-ALS with spectral non-negativity <strong>OFF</strong>; NMF not applicable</td></tr>
            <tr><td>ROA / VCD (4 files)</td><td>Many sharp bands like Raman, but <strong>signed</strong></td>
                <td>MCR-ALS with spectral non-negativity <strong>OFF</strong>; NMF not applicable</td></tr>
            <tr><td>Closed system (4 files)</td><td>DNA duplex melting into single strands;
                components sum to exactly 100%</td><td>MCR-ALS with <strong>Closure ON</strong> &mdash;
                the one case where closure is physically correct</td></tr>
        </table>

        <p>Within each family the <em>clean</em> and <em>noisy</em> versions share the same
        underlying truth, so the only difference is the noise.</p>

        <div class="warning"><strong>What they are really for.</strong> On the all-positive
        families (Raman, UV/Vis) the tools recover the true components well. The
        <strong>signed</strong> families are the instructive ones: they fit to nearly
        <em>zero lack-of-fit</em> and yet recover the true components only partially &mdash;
        a flawless-looking fit that is nonetheless wrong. Anchoring known components with
        <strong>Reference spectra</strong> lifts that recovery to near-perfect. Run these
        datasets once before trusting either method on real data; the contrast is the whole
        lesson.</div>

        <h2 id="troubleshooting">12. Troubleshooting</h2>

        <h3>Import Problems</h3>
        <table>
            <tr><th>Symptom</th><th>Cause</th><th>Solution</th></tr>
            <tr><td>No data imported</td><td>Wrong delimiter or decimal separator</td>
                <td>Open File → Import settings and set explicitly</td></tr>
            <tr><td>All data in one column</td><td>Delimiter not detected</td>
                <td>Set Value Separator manually</td></tr>
            <tr><td>Preview looks correct but import still fails or misreads columns</td>
                <td>A single stray tab/other delimiter character elsewhere in the file
                    outvoted the real delimiter during auto-detection</td>
                <td>Set Value Separator manually in Import settings — detection now
                    requires a majority of lines to agree, but an unusual file can
                    still confuse it</td></tr>
            <tr><td>Garbled numbers</td><td>Decimal separator mismatch</td>
                <td>Set Decimal Separator to . or , explicitly</td></tr>
            <tr><td>Wrong number of spectra</td><td>Interlaced format not detected</td>
                <td>Enable Interlaced Format in Import settings</td></tr>
        </table>

        <h3>Processing Problems</h3>
        <table>
            <tr><th>Symptom</th><th>Solution</th></tr>
            <tr><td>Combine Spectra or Calculator fails with x-axis error</td>
                <td>Apply Define Spectral Range → Apply linearisation first</td></tr>
            <tr><td>Can't find an Apply button for an operation</td>
                <td>Each operation's Apply / Add as New buttons are inside the dialog opened
                    by <strong>Run</strong> — not in the main window. Click Run first, then
                    look at the bottom of that dialog.</td></tr>
            <tr><td>Normalization regions not shown in dialog</td>
                <td>No regions defined yet — drag on the plot or enter From/To and click Add region</td></tr>
            <tr><td>Baseline correction produces unexpected results</td>
                <td>Ensure enough anchor points are placed (minimum 2) spanning the full x-range</td></tr>
        </table>

        <h3>Performance Problems</h3>
        <table>
            <tr><th>Symptom</th><th>Solution</th></tr>
            <tr><td>Slow interactive updates with many spectra</td>
                <td>Disable Interactive Update; enable only when needed</td></tr>
            <tr><td>Legend generation is slow</td>
                <td>Disable legend via ☰ Legend button; or limit Maximum Items</td></tr>
            <tr><td>Plot rendering slow</td>
                <td>Reduce selection to the spectra you need; use grid plot sparingly with &gt;50 spectra</td></tr>
        </table>

        <h3>Data Integrity</h3>
        <ul>
            <li>Save a snapshot before any irreversible operation</li>
            <li>Use the History dialog to verify the operation order is correct</li>
            <li>Check the counter (selected/total) before committing an operation</li>
            <li>An older Operations History entry showing a spectrum's
                <em>previous</em> name, after you've renamed it elsewhere, is expected
                — each rename creates its own entry, and older entries always show
                whichever name was true at that point in time</li>
        </ul>

        <!-- ═══════════════════════════════════════════════════════════
             INTEGRATION & REPRODUCIBILITY
             ═══════════════════════════════════════════════════════════ -->
        <h2>Integration with Other Software</h2>
        <ul>
            <li><strong>Export to CSV/Excel:</strong> compatible with MATLAB, R, Python pandas, Origin, SPSS</li>
            <li><strong>Plot export:</strong> PNG, PDF, SVG, EPS via matplotlib</li>
            <li><strong>Operations summary:</strong> exportable method documentation</li>
        </ul>

        <h2>Reproducibility &amp; Documentation</h2>
        <div class="tip"><ul>
            <li>Use <strong>History</strong> to record all processing steps and parameters</li>
            <li>Save <strong>snapshots</strong> at key analysis stages as audit-trail checkpoints</li>
            <li>Include metadata in exported results for traceability</li>
            <li>Test parameter settings on known standards before batch processing</li>
        </ul></div>

    </body>
    </html>
""")

    return help_template.safe_substitute(images)
