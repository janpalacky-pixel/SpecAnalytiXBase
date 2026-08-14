# src/help/data_range_help.py

"""
Help content for spectral data range selection functionality.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "data_range")

_SCREENSHOT_FILES = {
    "OVERVIEW":          "dialog_overview.png",
    "PLOT_SELECTION":    "interactive_range_selection.png",
    "DEFINED_RANGES":    "defined_ranges.png",
    "MODE":              "include_exclude_mode.png",
    "XAXIS_LIMITS":      "xaxis_limits.png",
    "LINEARIZATION":     "linearization_options.png",
    "COMMIT":            "commit_buttons.png",
}

# Cap displayed screenshot width at this many pixels — see
# svd_background_help.py for why explicit width/height attributes are
# used instead of relying on CSS to constrain image size.
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


def get_data_range_help_title():
    """Return the title for data range help."""
    return "Spectral Data Range Selection Help"


def get_data_range_help_content():
    """
    Get the HTML help content for spectral data range selection.

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
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2 { color: #1976D2; margin-top: 25px; }
            h3 { color: #F57C00; margin-top: 20px; }
            .method-category { background-color: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .warning { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; }
            .tip { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; }
            .danger { background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; border-radius: 5px; }
            .formula { background-color: #e9ecef; padding: 5px; font-family: monospace; border-radius: 3px; }
            ul { padding-left: 20px; }
            li { margin: 5px 0; }
            .parameter-box { background-color: #e8f5e8; padding: 10px; margin: 5px 0; border-left: 4px solid #4caf50; }
            .mode-box { background-color: #e3f2fd; padding: 10px; margin: 5px 0; border-left: 4px solid #2196f3; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>
        <h1>Spectral Data Range Selection Help</h1>
        
        <h2>Overview</h2>
        <p>The Data Range operation allows you to select specific spectral regions for analysis while excluding unwanted areas such as noise, artifacts, or irrelevant spectral features. This tool provides precise control over which parts of your spectra are included in subsequent analyses.</p>

        <div class="screenshot">
            <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="Spectral Data Range dialog overview" />
            <p class="caption">The full dialog: spectra list and controls on the left, interactive plot on the right.</p>
        </div>
        
        <div class="tip">
            <strong>Key Purpose:</strong> Focus analysis on spectral regions of interest while removing noise, artifacts, solvent peaks, or other unwanted features that could interfere with your results.
        </div>
        
        <h2>How It Works</h2>
        <p>The data range operation processes spectra by:</p>
        <ol>
            <li><strong>Range Definition:</strong> You define specific x-axis ranges (wavelength, wavenumber, etc.)</li>
            <li><strong>Mode Selection for data filtering:</strong> Choose whether to include or exclude the defined ranges</li>
            <li><strong>Optional Processing:</strong> Apply linearization to ensure uniform data spacing</li>
            <li><strong>Overall Range Limits:</strong> Optionally set minimum and maximum x-values for the entire spectrum</li>
        </ol>
        
        <h2>Parameters Explained</h2>
        
        <div class="parameter-box">
            <h3>Spectral Ranges</h3>
            <p><strong>Description:</strong> Specific x-axis intervals you want to include or exclude from analysis</p>
            <p><strong>How to Define:</strong></p>
            <ul>
                <li><strong>Interactive Plot Selection:</strong> Click and drag directly on the spectral plot to visually select ranges</li>
                <li><strong>Manual Entry:</strong> Type the two boundary values into the "From" and "To" fields, in either order</li>
                <li><strong>Multiple Ranges:</strong> Add as many ranges as needed using either method</li>
                <li><strong>Range Management:</strong> Select a range in the list to edit it in place (the "Add" button becomes "Update"), or Ctrl/Shift-click several (or Ctrl+A for all) and click "Remove" to delete them, using the buttons below the range list — click the orange "?" next to those buttons for a quick reminder</li>
                <li><strong>Visual Confirmation:</strong> All defined ranges are highlighted on the plot for immediate feedback</li>
            </ul>
            <p><strong>Examples:</strong></p>
            <ul>
                <li><strong>IR Spectroscopy:</strong> Select fingerprint region (800-1800 cm⁻¹)</li>
                <li><strong>Raman:</strong> Exclude laser line and filter artifacts</li>
                <li><strong>UV-Vis:</strong> Focus on specific absorption bands</li>
            </ul>
        </div>
        
        <div class="mode-box">
            <h3>Include vs. Exclude Mode</h3>

            <div class="screenshot">
                <img src="$MODE" width="$MODE_W" height="$MODE_H" alt="Include Ranges and Exclude Ranges radio buttons" />
                <p class="caption">The Range Mode group: "Include Ranges" and "Exclude Ranges" radio buttons.</p>
            </div>

            <p><strong>Note:</strong> Include and Exclude are offered purely for convenience — either one is, in principle, sufficient on its own, since an "include" selection is just the complement of an equivalent "exclude" selection (and vice versa). Pick whichever mode lets you describe your desired ranges with fewer, simpler entries.</p>

            <p><strong>Include Mode</strong> (the default): Keep ONLY the data within your defined ranges</p>
            <ul>
                <li><strong>Use when:</strong> You want to analyze specific spectral features</li>
                <li><strong>Result:</strong> Final spectrum contains only selected regions</li>
                <li><strong>Example:</strong> Keep only the C=O stretch region (1600-1800 cm⁻¹)</li>
            </ul>
            
            <p><strong>Exclude Mode:</strong> Remove the data within your defined ranges</p>
            <ul>
                <li><strong>Use when:</strong> You want to remove unwanted features but keep everything else</li>
                <li><strong>Result:</strong> Final spectrum has gaps where ranges were removed</li>
                <li><strong>Example:</strong> Remove solvent peaks while keeping all analyte signals</li>
            </ul>
        </div>
        
        <div class="parameter-box">
            <h3>X-Axis Limits (Optional)</h3>

            <div class="screenshot">
                <img src="$XAXIS_LIMITS" width="$XAXIS_LIMITS_W" height="$XAXIS_LIMITS_H" alt="X-Scale Range group with X-min and X-max fields and Reset buttons" />
                <p class="caption">The X-Scale Range group: X-min and X-max fields, each with a "Reset" button to restore the common intersection of the selected spectra (or their full combined range, if the selected spectra don't actually overlap).</p>
            </div>

            <p><strong>Description:</strong> Overall minimum and maximum x-values to limit the entire spectral range</p>
            <p><strong>Purpose:</strong> Limit the overall range before applying include/exclude ranges</p>
            <p><strong>Processing Order:</strong> Limits are applied FIRST, then include/exclude ranges</p>
            <p><strong>When to Use:</strong></p>
            <ul>
                <li><strong>Crop Spectra:</strong> Remove edge noise or irrelevant regions</li>
                <li><strong>Standardize Range:</strong> Ensure all spectra cover the same x-range</li>
                <li><strong>Focus Analysis:</strong> Concentrate on a specific spectral window</li>
            </ul>
        </div>
        
        <div class="parameter-box">
            <h3>Linearization</h3>

            <div class="screenshot">
                <img src="$LINEARIZATION" width="$LINEARIZATION_W" height="$LINEARIZATION_H" alt="Linearization group with Apply linearization checkbox and X-step field" />
                <p class="caption">The Linearization group: "Apply linearization" checkbox and the X-step field (enabled once linearization is checked).</p>
            </div>

            <p><strong>Description:</strong> Interpolates data to create uniform spacing between x-axis points</p>
            <p><strong>Step Size:</strong> Distance between consecutive x-values in the output</p>
            <p><strong>Benefits:</strong></p>
            <ul>
                <li><strong>Uniform Sampling:</strong> Ensures consistent data density</li>
                <li><strong>Algorithm Compatibility:</strong> Some analysis methods require uniform spacing (e.g. SVD analysis)</li>
                <li><strong>Data Standardization:</strong> Makes spectra from different instruments comparable</li>
            </ul>
            <p><strong>Interpolation Method:</strong> Uses cubic spline interpolation to preserve spectral shape</p>
            <div class="warning">
                <strong>Caution:</strong> Linearization can introduce small interpolation artifacts. Only use when necessary for your analysis.
            </div>
        </div>
        
        <h2>Usage Workflow</h2>
        
        <h3>Step-by-Step Process</h3>
        <ol>
            <li><strong>Select Spectra:</strong> Choose the spectra you want to process from the main program</li>
            <li><strong>Open Dialog:</strong> Select "Data range" from the Operations dropdown, then click "Parameters"</li>
            <li><strong>View Spectra:</strong> Your selected spectra appear in both the spectra list (left) and interactive plot (right)</li>
            <li><strong>Choose Display Spectra:</strong> Select which spectra to view in the plot for easier range selection</li>
            <li><strong>Set Overall Limits:</strong> Optionally define X-min/X-max to limit the entire spectral range</li>
            <li><strong>Define Ranges Interactively:</strong> Click and drag directly on the plot to select spectral ranges</li>
            <li><strong>Or Add Ranges Manually:</strong> Type the two boundary values into "From" and "To" (either order) and click "Add"</li>
            <li><strong>Manage Ranges:</strong> Click a range in the list to edit it in place ("Add" becomes "Update", with a "Cancel edit" button right next to it), or Ctrl/Shift-click several (or Ctrl+A for all) and click "Remove" to delete them</li>
            <li><strong>Choose Mode:</strong> Select Include or Exclude mode for your defined ranges</li>
            <li><strong>Configure Linearization:</strong> Enable if uniform spacing is needed</li>
            <li><strong>Commit Your Changes:</strong> Click "Apply" to replace the selected spectra with the range-restricted result, or "Add as New" to keep the originals untouched and add the result under new names</li>
        </ol>

        <div class="screenshot">
            <img src="$COMMIT" width="$COMMIT_W" height="$COMMIT_H" alt="Help, Apply, Add as New, and Close buttons" />
            <p class="caption">The dialog's commit buttons: Help on the left, then Apply, Add as New, and Close on the right.</p>
        </div>

        <div class="tip">
            <strong>Apply vs. Add as New vs. Close:</strong>
            <ul>
                <li><strong>Apply:</strong> Replaces the spectra you selected in the main window with their range-restricted result. The originals are overwritten once Apply runs.</li>
                <li><strong>Add as New:</strong> Leaves the originals completely untouched and adds the range-restricted result to the spectra list under new, unique names (for example <span class="formula">samplename_range</span>, with a number appended if that name is already taken).</li>
                <li><strong>Close:</strong> Closes the dialog without applying anything to the main window's spectra.</li>
            </ul>
            <p>There is no separate "Run" step for this operation — Apply and Add as New take effect immediately, with their own confirmation prompt shown right in the dialog, after which the dialog closes automatically. Whatever settings were last shown are still remembered the next time you reopen it for the same spectra, for example to try a few different ranges in a row.</p>
        </div>
        
        <h3>Interactive Range Selection</h3>
        <p>The dialog provides both visual plotting and list-based range management:</p>
        
        <div class="method-category">
            <h4>Visual Plot Interface</h4>

            <div class="screenshot">
                <img src="$PLOT_SELECTION" width="$PLOT_SELECTION_W" height="$PLOT_SELECTION_H" alt="Click-and-drag range selection on the spectral plot" />
                <p class="caption">Click and drag on the plot to select an x-range — it's added to the list automatically, shaded green (include) or red (exclude).</p>
            </div>

            <ul>
                <li><strong>Spectra Display:</strong> All your selected spectra are shown in the left panel list</li>
                <li><strong>Plot Selection:</strong> Choose which spectra to view in the plot by selecting them from the list</li>
                <li><strong>Interactive Selection:</strong> Click and drag directly on the plot to select x-ranges</li>
                <li><strong>Visual Feedback:</strong> Selected ranges appear as colored overlays on the plot</li>
                <li><strong>Zoom/Pan Tools:</strong> Use the toolbar to navigate and examine your spectral data closely. While the toolbar's Pan or Zoom tool is active, dragging on the plot pans/zooms instead of selecting a range — turn the tool off (click it again) to go back to drag-and-select</li>
                <li><strong>Coordinates Display:</strong> Mouse position shows exact x,y coordinates for precision</li>
            </ul>
        </div>
        
        <div class="method-category">  
            <h4>List-Based Management</h4>

            <div class="screenshot">
                <img src="$DEFINED_RANGES" width="$DEFINED_RANGES_W" height="$DEFINED_RANGES_H" alt="Defined Ranges group: range list, From/To fields, and Add (Update when editing) with Cancel edit next to it, Remove, and a small orange ? help button" />
                <p class="caption">The Defined Ranges group: the list of ranges, the "From"/"To" fields for manual entry, and the "Add" (becomes "Update" when editing, with "Cancel edit" right next to it) / "Remove" buttons, plus a small orange "?" button with a quick reminder of this workflow. Selecting a row in the list populates the From/To fields so you can edit it.</p>
            </div>

            <ul>
                <li><strong>"Add" Button:</strong> Adds the current From/To values as a new range — the two values can be entered in either order, they're sorted automatically. Adding values that exactly match a range already in the list is not allowed; that existing range is selected instead of creating a duplicate.</li>
                <li><strong>Editing a range:</strong> click it in the list — its values load into From/To, the button relabels itself "Update", and a "Cancel edit" button appears right next to it. Change the values and click "Update" to change that range in place; updating to values that exactly match a different existing range selects that range instead of creating a duplicate. "Cancel edit" leaves it unchanged and goes back to adding a new one.</li>
                <li><strong>Manual Entry:</strong> Type the two boundary x-values directly into the From/To fields</li>
                <li><strong>"Remove" Button:</strong> Deletes the selected range(s) from the list — Ctrl/Shift-click several ranges first (or Ctrl+A to select all) to remove more than one at a time; there's no separate "Clear All" button since Remove already covers that</li>
                <li><strong>Real-time Sync:</strong> Changes in the list immediately update the plot visualization</li>
            </ul>
        </div>

        <div class="tip">
            <strong>Best Workflow:</strong> Use the interactive plot to visually identify and select ranges, then fine-tune the exact values in the From/To fields if needed. Both methods work together seamlessly!
        </div>
        
        <h2>Common Use Cases</h2>
        
        <div class="method-category">
            <h3>Noise and Artifact Removal</h3>
            <p><strong>Scenario:</strong> Remove spectral regions with poor signal-to-noise ratio</p>
            <p><strong>Settings:</strong></p>
            <ul>
                <li><strong>Mode:</strong> Exclude</li>
                <li><strong>Ranges:</strong> Noisy edge regions, electronic artifacts</li>
                <li><strong>Example:</strong> Remove 0-400 cm⁻¹ and 3800-4000 cm⁻¹ noise in IR</li>
            </ul>
        </div>
        
        <div class="method-category">
            <h3>Solvent Peak Removal</h3>
            <p><strong>Scenario:</strong> Remove strong solvent absorptions that mask analyte peaks</p>
            <p><strong>Settings:</strong></p>
            <ul>
                <li><strong>Mode:</strong> Exclude</li>
                <li><strong>Ranges:</strong> Known solvent peak positions</li>
                <li><strong>Example:</strong> Remove water peaks at 1640 cm⁻¹ and 3200-3600 cm⁻¹</li>
            </ul>
        </div>
        
        <div class="method-category">
            <h3>Feature-Specific Analysis</h3>
            <p><strong>Scenario:</strong> Focus analysis on specific molecular vibrations or transitions</p>
            <p><strong>Settings:</strong></p>
            <ul>
                <li><strong>Mode:</strong> Include</li>
                <li><strong>Ranges:</strong> Spectral regions containing features of interest</li>
                <li><strong>Example:</strong> Analyze only C-H stretch region (2800-3000 cm⁻¹)</li>
            </ul>
        </div>
        
        
        <div class="method-category">
            <h3>Data Standardization</h3>
            <p><strong>Scenario:</strong> Ensure all spectra cover identical x-ranges</p>
            <p><strong>Settings:</strong></p>
            <ul>
                <li><strong>X-Limits:</strong> Set common minimum and maximum values</li>
                <li><strong>Linearization:</strong> Enable with consistent step size</li>
                <li><strong>Example:</strong> Standardize all IR spectra to 600-4000 cm⁻¹ with 1 cm⁻¹ steps</li>
            </ul>
        </div>
        
        <div class="method-category">
            <h3>Spectral Segmentation</h3>
            <p><strong>Scenario:</strong> Create focused spectral segments for specialized analysis</p>
            <ul>
                <li><strong>Functional Group Analysis:</strong> Isolate specific molecular vibrations</li>
                <li><strong>Baseline Simplification:</strong> Select regions with minimal baseline curvature</li>
                <li><strong>Peak Fitting:</strong> Extract individual peak regions for detailed analysis</li>
                <li><strong>Time-Series Analysis:</strong> Focus on regions that change over time</li>
            </ul>
        </div>
        
        <h2>Best Practices</h2>
        
        <h3>Linearization Considerations</h3>
        <ul>
            <li><strong>Enable When:</strong> Algorithms require uniform spacing, data fusion, or statistical analysis</li>
            <li><strong>Step Size Selection:</strong> Match or slightly exceed your original data resolution</li>
            <li><strong>Quality Check:</strong> Compare linearized and original spectra for interpolation artifacts</li>
            <li><strong>Performance Impact:</strong> Linearization increases processing time for large datasets</li>
        </ul>
        
        <h2>Technical Details</h2>
        
        <h3>Processing Order</h3>
        <p>The data range operation applies transformations in this specific order:</p>
        <ol>
            <li><strong>X-Axis Limits:</strong> Crop spectrum to overall min/max bounds</li>
            <li><strong>Linearization:</strong> Interpolate to uniform spacing (if enabled)</li>
            <li><strong>Range Selection:</strong> Apply include/exclude ranges</li>
        </ol>
        
        <div class="warning">
            <strong>Important:</strong> This processing order means that x-axis limits are applied before range selection. Set limits appropriately to avoid unintended data loss.
        </div>
        
        <h3>Interpolation Algorithm</h3>
        <p>When linearization is enabled, the system uses cubic spline interpolation:</p>
        <ul>
            <li><strong>Method:</strong> SciPy CubicSpline with natural boundary conditions</li>
            <li><strong>Advantages:</strong> Smooth interpolation, preserves spectral shape</li>
            <li><strong>Handling:</strong> Automatically sorts data and removes duplicate x-values</li>
            <li><strong>Edge Cases:</strong> Gracefully handles insufficient data points</li>
        </ul>
        
        <h3>Range Handling</h3>
        <p>How defined ranges are processed when applied:</p>
        <ul>
            <li><strong>Normalization:</strong> When a range is applied, its boundaries are matched to data-point indices using the lower and higher index regardless of which one was entered first, so a reversed range still works correctly at apply time. The "From"/"To" fields don't need to be in low-to-high order for this same reason — whichever order you type the two boundaries in, "Add" sorts them automatically; dragging on the plot always produces an already-ordered range too.</li>
            <li><strong>Overlaps:</strong> Overlapping ranges are combined into a single selection rather than conflicting or being double-counted</li>
            <li><strong>Precision:</strong> Each range boundary is matched to the nearest existing x-value in that spectrum's own data, not interpolated, so the exact cut point can differ slightly between spectra with different x-scales</li>
            <li><strong>Empty Results:</strong> If the X-axis limits or the defined ranges leave a spectrum with no data points, that spectrum is left empty and a warning is logged so the situation isn't silently missed</li>
        </ul>
        
        <h2>Troubleshooting</h2>
        
        <h3>Common Issues and Solutions</h3>
        
        <div class="danger">
            <h4>Problem: No data remaining after range selection</h4>
            <p><strong>Causes:</strong> Ranges don't overlap with actual data, incorrect mode selection</p>
            <p><strong>Solutions:</strong> Check x-axis values, verify include/exclude mode, adjust range boundaries. A warning is logged for any spectrum left with no data points, which can help identify which spectrum and setting caused it.</p>
        </div>
        
        <div class="danger">
            <h4>Problem: Important peaks are missing</h4>
            <p><strong>Causes:</strong> Accidentally excluded relevant ranges, incorrect range boundaries</p>
            <p><strong>Solutions:</strong> Review range definitions, switch to exclude mode if appropriate</p>
        </div>
        
        <div class="danger">
            <h4>Problem: Linearization creates artifacts</h4>
            <p><strong>Causes:</strong> Step size too large, insufficient original data points</p>
            <p><strong>Solutions:</strong> Reduce step size, check original data quality, disable linearization if not needed</p>
        </div>
        
        <div class="danger">
            <h4>Problem: Processing is very slow</h4>
            <p><strong>Causes:</strong> Very small linearization step size, large datasets</p>
            <p><strong>Solutions:</strong> Increase step size, apply x-axis limits first to reduce data volume</p>
        </div>
        
        <h3>Data Quality Checks</h3>
        <ul>
            <li><strong>Visual Inspection:</strong> Always plot the processed spectra to verify results</li>
            <li><strong>Peak Preservation:</strong> Ensure important spectral features are retained</li>
            <li><strong>Continuity:</strong> Check that remaining spectral regions make analytical sense</li>
            <li><strong>Resolution:</strong> Verify that linearization doesn't degrade resolution</li>
        </ul>
        
        <h2>Integration with Other Operations</h2>
        
        <h3>Recommended Operation Sequence</h3>
        <div class="tip">
            <h4>Typical Processing Pipeline:</h4>
            <ol>
                <li><strong>Data Range:</strong> Remove noise and select regions of interest</li>
                <li><strong>Baseline Correction:</strong> Apply to cleaned spectral regions</li>
                <li><strong>Normalization:</strong> Normalize the processed data</li>
                <li><strong>Smoothing:</strong> Apply if needed for noise reduction</li>
                <li><strong>Analysis:</strong> Perform statistical or chemometric analysis</li>
            </ol>
        </div>
        
        <h3>Synergistic Operations</h3>
        <ul>
            <li><strong>Before Baseline Correction:</strong> Remove regions that complicate baseline fitting</li>
            <li><strong>Before Peak Detection:</strong> Focus on regions containing relevant peaks</li>
            <li><strong>Before Multivariate Analysis:</strong> Remove non-informative or noisy regions</li>
            <li><strong>Before Data Fusion:</strong> Standardize spectral ranges across datasets</li>
        </ul>
        
        <h2>Spectral Type Considerations</h2>
        
        <h3>Infrared (IR) Spectroscopy</h3>
        <ul>
            <li><strong>Common Exclusions:</strong> 2000-2500 cm⁻¹ (if no triple bonds), edge noise regions</li>
            <li><strong>Functional Group Focus:</strong> C=O (1600-1800), C-H (2800-3000), O-H (3200-3600)</li>
            <li><strong>Fingerprint Region:</strong> 600-1500 cm⁻¹ for molecular identification</li>
        </ul>
        
        <h3>Raman Spectroscopy</h3>
        <ul>
            <li><strong>Laser Line Removal:</strong> Exclude strong laser scatter (usually 0-100 cm⁻¹)</li>
            <li><strong>Filter Artifacts:</strong> Remove edge filter cutoff regions</li>
            <li><strong>Low Frequency:</strong> Focus on 100-1800 cm⁻¹ for most organic molecules</li>
        </ul>
        
        <h3>UV-Visible Spectroscopy</h3>
        <ul>
            <li><strong>Absorption Bands:</strong> Focus on λmax regions for specific chromophores</li>
            <li><strong>Scattering Removal:</strong> Exclude regions with strong scattering artifacts</li>
            <li><strong>Solvent Cutoff:</strong> Remove regions where solvent absorbs</li>
        </ul>
        
        <div class="tip">
            <h3>Pro Tips for Easy Range Selection</h3>
            <ul>
                <li><strong>Start Visual:</strong> Use the interactive plot to quickly identify ranges of interest</li>
                <li><strong>Zoom First:</strong> Use the plot toolbar's zoom/pan tools to focus on a region before selecting — toggle the tool off again afterward to go back to click-and-drag range selection (the two don't conflict, but only one is active at a time)</li>
                <li><strong>Fine-tune in the List:</strong> After plot selection, adjust exact values in the From/To fields if needed</li>
                <li><strong>Use Coordinates:</strong> Watch the coordinates display to see exact x,y values while moving mouse</li>
                <li><strong>Multiple Views:</strong> Select different spectra from the list to compare and identify common features</li>
                <li><strong>Iterative Process:</strong> Add ranges one at a time and see immediate visual feedback</li>
                <li><strong>Document Decisions:</strong> Record which ranges you selected and why for reproducibility</li>
            </ul>
        </div>
        
        <p>The Data Range operation is a powerful tool for focusing spectroscopic analysis on regions of interest while removing problematic areas. When used thoughtfully, it can significantly improve the quality and reliability of subsequent analyses by ensuring that only high-quality, relevant spectral data is included in your results.</p>
        
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

    return help_template.safe_substitute(images)
