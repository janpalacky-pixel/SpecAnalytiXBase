# src/help/peak_fitting_help.py

"""
Help content for the Peak Fitting & Deconvolution operation.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "peak_fitting")

_SCREENSHOT_FILES = {
    "OVERVIEW":      "dialog_overview.png",
    "PLOT":          "plot_area.png",
    "TABLE":         "peaks_table.png",
    "ADD_CONTROLS":  "peak_adding_controls.png",
    "WIDTH_DIALOG":  "initial_width_dialog.png",
    "FIT_CONTROLS":  "fitting_controls.png",
    "OUTPUT_OPTIONS":"output_options.png",
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


def get_peak_fitting_help_title():
    return "Peak Fitting & Deconvolution Help"


def get_peak_fitting_help_content():
    """Return HTML content for comprehensive user guide help."""
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which
    # would collide with .format()-style placeholders.
    help_template = Template("""
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { color: #1976D2; margin-top: 1.5em; }
            .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin-top: 10px; }
            .key-feature { background-color: #e3f2fd; padding: 10px; border-left: 4px solid #1e88e5; margin-top: 10px;}
            .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace;}
            li { margin-bottom: 5px; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>
        <h1>Peak Fitting & Deconvolution Help</h1>

        <h2>Overview</h2>
        <p>The Peak Fitting tool allows you to model peaks in your spectrum with mathematical functions (Gaussian, Lorentzian, Voigt, or Pseudo-Voigt). This is essential for deconvolving overlapping peaks and accurately quantifying their properties such as <b>Center</b>, <b>Height</b>, <b>Area</b>, and <b>Full Width at Half Maximum (FWHM)</b>.</p>
        <p>Fitting is always performed on the <b>full spectrum</b>. You can use the <b>Zoom</b> (magnifying glass) and <b>Pan</b> (cross-arrows) tools from the plot's navigation toolbar to get a closer look at specific regions. Click the <b>Home</b> button (house icon) to reset the view.</p>

        <div class="screenshot">
            <img src="$OVERVIEW" width="${OVERVIEW_W}" height="${OVERVIEW_H}" alt="Peak Fitting dialog: Peaks to Fit table and controls on the left, plot with fitted peaks on the right" />
            <p class="caption">The full Peak Fitting dialog: the peaks table and fitting controls on the left, plot and residual on the right.</p>
        </div>

        <h2 id="models">Peak shapes</h2>
        <table style="border-collapse:collapse; width:100%;">
            <tr style="background:#f1f1f1;"><th style="text-align:left; padding:4px 8px;">Model</th><th style="text-align:left; padding:4px 8px;">Parameters</th><th style="text-align:left; padding:4px 8px;">Use when</th></tr>
            <tr><td style="padding:4px 8px;"><b>Gaussian</b></td><td style="padding:4px 8px;">Center, Amplitude, Width (σ)</td>
                <td style="padding:4px 8px;">Peak broadening is dominated by Doppler/thermal effects or instrument resolution — the most common case for Raman/IR bands.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Lorentzian</b></td><td style="padding:4px 8px;">Center, Amplitude, Width (γ)</td>
                <td style="padding:4px 8px;">Peak broadening is dominated by lifetime/pressure effects — often seen in gas-phase spectra or homogeneously-broadened transitions.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Voigt</b></td><td style="padding:4px 8px;">Center, Amplitude, Width (σ), Extra (γ)</td>
                <td style="padding:4px 8px;">Real peaks are almost always a genuine mix of both broadening mechanisms. Voigt is the true convolution of a Gaussian (σ) and a Lorentzian (γ) — the most physically accurate choice when you need to know the actual Gaussian/Lorentzian balance, at the cost of being the slowest of the four to fit.</td></tr>
            <tr><td style="padding:4px 8px;"><b>Pseudo-Voigt</b></td><td style="padding:4px 8px;">Center, Amplitude, Width (shared FWHM), Extra (η, 0&ndash;1)</td>
                <td style="padding:4px 8px;">A faster, widely-used approximation to Voigt — a straight linear blend of a Gaussian and Lorentzian that share the same FWHM and height, weighted by η (0 = pure Gaussian, 1 = pure Lorentzian). Standard in XRD and Raman fitting software when speed matters more than the small accuracy difference from true Voigt.</td></tr>
        </table>
        <div class="tip">
            <strong>Not sure which to pick?</strong> Start with Gaussian (fastest, works well for most Raman/IR bands). If the fit's residual shows systematic wings the Gaussian can't capture, try Voigt or Pseudo-Voigt — both let the fit find how much Lorentzian character the peak actually has, rather than forcing an all-or-nothing choice between Gaussian and Lorentzian.
        </div>

        <h2>Recommended Workflow</h2>
        <ol>
            <li>The <b>"Add via Click"</b> checkbox is enabled by default. Click directly on the plot at the top of a peak to add it.</li>
            <li>(Optional) To change the default width for new peaks, <b>right-click the "Auto-Detect Peaks" button</b> and select <b>"Set Initial Peak Width..."</b>.</li>
            <li>(Optional) Click <b>"Auto-Detect Peaks"</b> to let the algorithm find initial peaks for you. It will skip peaks that are already in the list.</li>
            <li>Refine the initial guesses in the <b>"Peaks to Fit"</b> table. Good initial guesses are crucial for a successful fit.</li>
            <li>Select an <b>"Amplitude Constraint"</b> (e.g., "Positive Peaks Only") if needed.</li>
            <li>Click the <b>"Fit Peaks"</b> button. The plot will update with the new results.</li>
            <li>Review the <b>"Total Fit"</b> (red line) and the <b>"Residual"</b> (bottom plot). If the fit is poor, adjust your initial guesses and fit again.</li>
            <li>(Optional) Click <b>"Copy Results"</b> to copy the parameters from the table to your clipboard.</li>
            <li><b>Select at least one "Output Option"</b> (checkbox) if you want to keep anything from this fit — see below for exactly what happens if you don't.</li>
            <li>Click <b>OK</b> to finish.</li>
        </ol>

        <h2>The Interface Explained</h2>

        <h3>The Plot</h3>
        <ul>
            <li><b>Gray Circles (Original Data):</b> Your raw spectrum data.</li>
            <li><b>Dashed Lines (Initial Guesses):</b> The peaks from the table *before* fitting. This shows what the algorithm is starting with.</li>
            <li><b>Red Line (Total Fit):</b> The sum of all individual fitted peaks. This is the final model that best matches your data.</li>
            <li><b>Dotted Lines (Individual Peaks):</b> The final, fitted shape of each component peak.</li>
            <li><b>Bottom Plot (Residual):</b> The error (Original Data - Total Fit). A good fit will have a small, random residual centered around zero.</li>
        </ul>

        <div class="screenshot">
            <img src="$PLOT" width="${PLOT_W}" height="${PLOT_H}" alt="Fitted peaks plot with gray original data, dashed initial guesses, red total fit, dotted individual peaks, and the residual plot below" />
            <p class="caption">The plot: original data (gray circles), total fit (red), individual peaks (dotted), and the residual below.</p>
        </div>

        <h3>The 'Peaks to Fit' Table</h3>
        <p>This table is your main control center for managing peaks.</p>
        <div class="key-feature">
            <h4>Key Table Features:</h4>
            <ul>
                <li><b>Color (Column 1):</b> Shows the peak's color on the plot. <b>Double-click this swatch to change the color.</b></li>
                <li><b>Model:</b> Change the peak shape — Gaussian, Lorentzian, Voigt, or Pseudo-Voigt (see <a href="#models">Peak shapes</a> below).</li>
                <li><b>Extra (γ/η):</b> The 4th parameter that Voigt and Pseudo-Voigt need beyond Center/Amplitude/Width — shown as "—" and disabled for Gaussian/Lorentzian, since they don't have one.</li>
                <li><b>Parameters (Center, Amplitude, Width):</b> Double-click any cell to edit its value. <b>This is the most important step for improving a bad fit.</b></li>
                <li><b>Delete Peaks:</b> Select one or more rows and press the <b>Delete</b> key on your keyboard, or use the "Remove Selected Peak(s)" button.</li>
            </ul>
        </div>

        <div class="screenshot">
            <img src="$TABLE" width="${TABLE_W}" height="${TABLE_H}" alt="Peaks to Fit table with Color, Model, Center, Amplitude, Width, and Extra columns" />
            <p class="caption">The Peaks to Fit table — double-click the color swatch or any parameter cell to edit it.</p>
        </div>

        <h3>Peak Adding Controls</h3>
        <ul>
            <li><b>Auto-Detect Peaks:</b> Finds peaks automatically and adds them to the list. It will not add peaks that have a similar center to ones already in the list.</li>
            <li><b>Add via Click (Checkbox):</b> When checked (default), you can click on the plot to add a peak. The peak's 'Center' and 'Amplitude' will be set by where you click, and the 'Width' will be set by the "Initial Peak Width". This disables the toolbar's Zoom/Pan.</li>
            <li><b>Set Initial Peak Width... (Context Menu):</b> <b>Right-click the "Auto-Detect Peaks" button</b> to open a dialog. The value you set here is used as the initial 'Width' for all peaks added using "Add via Click".</li>
        </ul>

        <div class="screenshot">
            <img src="$ADD_CONTROLS" width="${ADD_CONTROLS_W}" height="${ADD_CONTROLS_H}" alt="Auto-Detect Peaks button and Add via Click checkbox above the peaks table" />
            <p class="caption">Peak adding controls: Auto-Detect Peaks (right-click for width settings) and Add via Click.</p>
        </div>

        <div class="screenshot">
            <img src="$WIDTH_DIALOG" width="${WIDTH_DIALOG_W}" height="${WIDTH_DIALOG_H}" alt="Set Initial Peak Width dialog, opened by right-clicking Auto-Detect Peaks" />
            <p class="caption">The "Set Initial Peak Width..." dialog, opened via right-click on Auto-Detect Peaks.</p>
        </div>

        <h3>Fitting Controls</h3>
        <ul>
            <li><b>Amplitude Constraint:</b> Forces the fit to find only positive, only negative, or any (unrestricted) peaks.</li>
            <li><b>Fit Peaks:</b> Runs the optimization algorithm to find the best parameters based on your initial guesses.</li>
            <li><b>Copy Results:</b> Becomes active when there are peaks in the table. This copies the <b>current values in the table</b> (plus calculated FWHM and Area) to your clipboard in a tab-separated format, ready to be pasted into Excel or PowerPoint.</li>
        </ul>

        <div class="screenshot">
            <img src="$FIT_CONTROLS" width="${FIT_CONTROLS_W}" height="${FIT_CONTROLS_H}" alt="Amplitude Constraint dropdown, Fit Peaks button, and Copy Results button" />
            <p class="caption">Fitting controls: Amplitude Constraint, Fit Peaks, and Copy Results.</p>
        </div>

        <h3>Output Options (Adds New Spectra)</h3>
        <p>These are all optional. When checked, they will <b>add</b> new spectra to your main list. The original spectrum is never replaced, and its own data and metadata are never modified — see <a href="#ok-behavior">What Happens When You Click OK?</a> below.</p>
        <ul>
            <li><b>Add spectrum from total fit:</b> Adds a new spectrum showing only the combined red "Total Fit" line, named <code>&lt;original label&gt;_fit</code>.</li>
            <li><b>Add spectrum from residual:</b> Adds a new spectrum showing only the purple "Residual" line, named <code>&lt;original label&gt;_residual</code>.</li>
            <li><b>Add new spectra from individual peaks:</b> Adds each dotted-line component as its own new spectrum, named <code>&lt;original label&gt;_peak_01</code>, <code>_peak_02</code>, and so on — zero-padded so they sort correctly in the main spectrum list even with 10 or more peaks (without the padding, "peak_10" would alphabetically sort before "peak_2").</li>
        </ul>

        <div class="screenshot">
            <img src="$OUTPUT_OPTIONS" width="${OUTPUT_OPTIONS_W}" height="${OUTPUT_OPTIONS_H}" alt="Output Options checkboxes: add spectrum from total fit, from residual, and from individual peaks" />
            <p class="caption">Output Options — check at least one before clicking OK to keep anything from the fit.</p>
        </div>

        <div class="key-feature" id="ok-behavior">
            <h3>What Happens When You Click OK?</h3>
            <p><b>Nothing is saved unless you check at least one Output Option.</b> Fitting a spectrum is treated as analysis, not a change to that spectrum's data — the original spectrum's data and metadata are never touched by fitting alone, regardless of how good or bad the fit was.</p>
            <ol>
                <li><b>If no Output Options are checked:</b> the fit is discarded once you close the dialog. Nothing is added to the spectrum list, nothing is written to the original spectrum's metadata, and this doesn't appear as a step in Operations History. If you want to keep anything from a fit, check at least one Output Option before clicking OK.</li>
                <li><b>If any Output Options are checked:</b> the corresponding new spectra (fit / residual / individual peaks) are created and added to your main list. Each one carries its own metadata describing exactly how it was produced — which model, which parameters, and which spectrum it came from — viewable via that spectrum's own Metadata panel. These new spectra do <b>not</b> inherit the original spectrum's import details (file path, column index, etc.), since they were computed, not imported.</li>
            </ol>
        </div>

        <div class="tip">
            <strong>Pro Tip for a Good Fit:</strong> The algorithm is only as good as your initial guesses. If the fit looks bad, the most common reason is a poor initial guess. Try manually editing the 'Center', 'Amplitude', or 'Width' in the table to be closer to what you see, then click "Fit Peaks" again.
        </div>
    </body>
    </html>
    """)

    return help_template.safe_substitute(images)
