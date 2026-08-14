# src/help/svd_background_help.py

"""
Help content for SVD background correction functionality.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "svd_baseline")

_SCREENSHOT_FILES = {
    "OVERVIEW":          "dialog_overview.png",
    "SUBSPECTRUM_NAV":   "subspectrum_navigation.png",
    "ENABLE":            "enable_baseline_correction.png",
    "POINTS_ADDED":      "baseline_points_added.png",
    "VIEW_ORIGINAL":     "view_mode_original.png",
    "VIEW_CORRECTED":    "view_mode_corrected.png",
    "VIEW_BOTH":         "view_mode_both.png",
    "FITTING":           "baseline_fitting_methods.png",
    "CLEAR":             "clear_baselines_buttons.png",
    "RECON_MODE":        "reconstruction_mode_buttons.png",
    "COMPONENTS_MENU":   "components_list_context_menu.png",
    "SINGULAR_VALUES":   "singular_values_window.png",
    "PREVIEW_WINDOW":    "preview_reconstruction_window.png",
    "COMMIT":            "commit_buttons.png",
    "CANVAS_MENU":       "canvas_context_menu.png",
}

# Cap displayed screenshot width at this many pixels — see
# baseline_correction_help.py for why explicit width/height attributes are
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


def get_svd_background_help_content():
    """
    Get the HTML help content for SVD background correction.
    
    Returns:
        str: HTML formatted help content
    """
    images = _resolve_screenshot_uris()

    # string.Template ($NAME placeholders), not str.format()/f-strings — the
    # CSS block below is full of literal { } braces that would collide with
    # .format()-style placeholders.
    help_template = Template("""<!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            h2 { color: #34495e; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px; margin-top: 25px; }
            h3 { color: #7f8c8d; margin-top: 20px; }
            .section { margin-bottom: 20px; }
            .highlight { background-color: #f8f9fa; padding: 10px; border-left: 4px solid #3498db; margin: 10px 0; }
            .warning { background-color: #fff5f5; padding: 10px; border-left: 4px solid #e74c3c; margin: 10px 0; }
            .tip { background-color: #f0fff4; padding: 10px; border-left: 4px solid #27ae60; margin: 10px 0; }
            .control { font-weight: bold; color: #2980b9; }
            .math { font-family: 'Times New Roman', serif; font-style: italic; }
            ul { margin-left: 20px; }
            li { margin-bottom: 5px; }
            .method-box { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .equation { text-align: center; margin: 15px 0; padding: 10px; background-color: #f8f9fa; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>
        <h1>SVD Background Correction Help</h1>
        
        <div class="section">
            <h2>Overview</h2>
            <p>SVD (Singular Value Decomposition) background correction is an advanced mathematical technique for removing systematic background patterns from sets of spectra. It decomposes your spectra into mathematical components (subspectra) and allows you to selectively remove background-related components while preserving spectral features.</p>
            
            <div class="highlight">
                <strong>Key Concept:</strong> SVD separates your spectra into independent components ranked by their contribution to variance. Background patterns typically appear in the first few components and can be corrected by interactive baseline subtraction before reconstruction.
            </div>
            
            <div class="equation">
                <span class="math">Data Matrix = U × S × V<sup>T</sup></span><br>
                Where: U = subspectra, S = singular values, V<sup>T</sup> = coefficients
            </div>
            
            <p>This method is particularly powerful because it can identify and remove systematic variations that affect multiple spectra simultaneously, such as instrumental drift, temperature effects, or common background interferences.</p>
        </div>

        <div class="section">
            <h2>Interface Layout</h2>

            <div class="screenshot">
                <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="SVD Background Correction dialog overview" />
                <p class="caption">The full dialog: analysis controls on the left, subspectrum and coefficients plots on the right.</p>
            </div>
            
            <h3>Left Panel - Analysis Controls</h3>
            <ul>
                <li><span class="control">Subspectrum Navigation:</span> Browse through individual components with Previous/Next buttons and spinbox</li>
                <li><span class="control">Baseline Correction:</span> Interactive baseline editing for subspectra with On/Off toggle</li>
                <li><span class="control">Reconstruction Mode:</span> Choose which components to use for final reconstruction</li>
                <li><span class="control">Selected Components:</span> Comprehensive list showing variance, singular values, and residual errors</li>
            </ul>
            
            <h3>Right Panel - Interactive Visualization</h3>
            <ul>
                <li>Top plot: Current subspectrum with optional baseline correction visualization</li>
                <li>Bottom plot: Coefficients for the current subspectrum (can be toggled on/off)</li>
                <li>Full navigation toolbar for zooming, panning, and detailed examination</li>
                <li>Coordinate display showing current mouse position</li>
            </ul>
            
            <div class="tip">
                <strong>Layout Tip:</strong> You can hide the left control panel by right-clicking on the plot and selecting "Show Only SVD Results" to maximize the visualization area.
            </div>
        </div>

        <div class="section">
            <h2>Complete SVD Analysis Workflow</h2>
            
            <h3>1. Automatic SVD Computation</h3>
            <div class="method-box">
                <p>When you open the SVD Background Correction dialog, the following happens automatically:</p>
                <ul>
                    <li>SVD is computed from all selected spectra using numpy's efficient implementation</li>
                    <li>All selected spectra must have identical x-axes (wavelength/wavenumber ranges)</li>
                    <li>Components are automatically ranked by explained variance (highest contribution first)</li>
                    <li>The first few components typically contain 80-95% of the total variance</li>
                    <li>Explained variance percentages are calculated for each component</li>
                    <li>Singular values and residual errors are computed for component assessment</li>
                </ul>
                
                <div class="tip">
                    <strong>Interpretation Guide:</strong> Component 1 usually contains the main spectral features and highest variance. Component 2 often represents the most significant systematic variation (like baseline drift). Later components progressively represent smaller variations, noise, or instrument artifacts.
                </div>
                
                <div class="warning">
                    <strong>Important:</strong> If SVD computation fails, check that all your spectra share the same x-axis (same range and point count). Floating-point round-off from an arithmetically rebuilt axis (e.g. Data Range linearisation) is tolerated automatically — genuinely different sampling grids are what actually need reconciling, typically with the Data Range operation first.
                </div>
            </div>
            
            <h3>2. Detailed Subspectrum Examination</h3>
            <div class="method-box">
                <p>After SVD computation, you need to examine each subspectrum to understand what it represents:</p>
                <ul>
                    <li>Use <span class="control">Previous/Next</span> buttons or directly enter component numbers in the spinbox</li>
                    <li>Each subspectrum shows its explained variance percentage in the title</li>
                    <li>Look carefully for baseline-like patterns: smooth, monotonic curves that don't resemble real spectral features</li>
                    <li>Sharp peaks or detailed structure usually indicate real spectral information that should be preserved</li>
                    <li>Use <span class="control">Invert</span> button if a subspectrum appears upside-down (this preserves mathematical correctness)</li>
                    <li>The coefficients plot shows how this subspectrum contributes across your dataset</li>
                </ul>

                <div class="screenshot">
                    <img src="$SUBSPECTRUM_NAV" width="$SUBSPECTRUM_NAV_W" height="$SUBSPECTRUM_NAV_H" alt="Subspectrum navigation controls" />
                    <p class="caption">Previous / Next / "Jump to:" spinbox / Invert.</p>
                </div>
                
                <div class="highlight">
                    <strong>What to Look For in Subspectra:</strong><br>
                    • <strong>Baseline-like:</strong> Smooth, gradually changing curves without sharp features<br>
                    • <strong>Spectral features:</strong> Sharp peaks, valleys, or detailed structure<br>
                    • <strong>Noise:</strong> Random, irregular variations (usually in higher-numbered components)<br>
                    • <strong>Artifacts:</strong> Systematic patterns that don't match expected spectral behavior
                </div>
                
                <div class="tip">
                    <strong>Component Analysis Strategy:</strong> Start with Component 1 (highest variance) and work your way down. Focus your baseline correction efforts on the first 3-5 components, as these contain most of the systematic variations worth correcting.
                </div>
            </div>
            
            <h3>3. Interactive Baseline Correction of Subspectra</h3>
            <div class="method-box">
                <h4>Enabling Baseline Correction Mode:</h4>
                <ul>
                    <li>Ensure <span class="control">"On"</span> is selected in the "Enable Baseline Correction" section</li>
                    <li>Baseline editing only works in <span class="control">"Original"</span> and <span class="control">Both</span> view modes</li>
                    <li>The plot should show the raw subspectrum in blue with interactive capability enabled</li>
                    <li>Mouse cursor changes indicate that baseline editing is active</li>
                </ul>

                <div class="screenshot">
                    <img src="$ENABLE" width="$ENABLE_W" height="$ENABLE_H" alt="Enable Baseline Correction On/Off control" />
                    <p class="caption">The Enable Baseline Correction control, with "On" selected.</p>
                </div>
                
                <h4>Adding and Removing Baseline Points:</h4>
                <ul>
                    <li><strong>Left-click:</strong> Add baseline points (displayed as red circles with black borders)</li>
                    <li><strong>Right-click:</strong> Remove the nearest baseline point within tolerance</li>
                    <li>You need at least 2 points to generate a baseline curve</li>
                    <li>More points provide better baseline shape control but require more careful placement</li>
                    <li>Points are automatically sorted by x-coordinate for proper curve fitting</li>
                </ul>

                <div class="screenshot">
                    <img src="$POINTS_ADDED" width="$POINTS_ADDED_W" height="$POINTS_ADDED_H" alt="Baseline points placed on a subspectrum" />
                    <p class="caption">Baseline points (red, black-edged) placed on a subspectrum, with the fitted baseline curve.</p>
                </div>
                
                <h4>Baseline Fitting Options:</h4>
                <ul>
                    <li><span class="control">Spline:</span> Cubic spline interpolation - creates smooth, natural-looking baselines (recommended for most cases)</li>
                    <li><span class="control">Poly:</span> Polynomial fitting with adjustable order - provides mathematical control over baseline shape</li>
                    <li>For polynomial fitting, adjust the order (1-10) to control complexity - higher orders can fit more complex shapes but may overfit</li>
                    <li>The baseline curve updates automatically as you add, remove, or modify points</li>
                </ul>

                <div class="screenshot">
                    <img src="$FITTING" width="$FITTING_W" height="$FITTING_H" alt="Baseline Fitting controls: Spline, Poly, and Polynomial Order" />
                    <p class="caption">Spline vs. Poly fitting, with the Polynomial Order spinner.</p>
                </div>
                
                <h4>View Modes for Assessment:</h4>
                <p>Use the <span class="control">Original</span>, <span class="control">Corrected</span>, and
                <span class="control">Both</span> buttons to switch how the current subspectrum is displayed —
                see the <a href="#svd-view-modes">View Modes</a> section below for what each one shows.</p>

                <div class="warning">
                    <strong>Baseline Correction Best Practices:</strong><br>
                    • Only apply baseline correction to subspectra that clearly show baseline-like behavior<br>
                    • Avoid correcting subspectra with sharp spectral features<br>
                    • Place baseline points in regions that represent true background, not spectral features<br>
                    • Use the minimum number of points necessary to capture the baseline shape<br>
                    • Always check the "Corrected" view to ensure you haven't removed important spectral information
                </div>
            </div>
        </div>

        <div class="section" id="svd-view-modes">
            <h2>View Modes</h2>

            <div class="method-box">
                <h3><span class="control">Original</span></h3>
                <ul>
                    <li>Shows the raw subspectrum (blue) with baseline points (red, black-edged) and the fitted baseline curve</li>
                    <li>Use this mode for placing and adjusting baseline points</li>
                </ul>

                <div class="screenshot">
                    <img src="$VIEW_ORIGINAL" width="$VIEW_ORIGINAL_W" height="$VIEW_ORIGINAL_H" alt="Original view mode" />
                    <p class="caption">Original view: subspectrum (blue), baseline points and curve (red).</p>
                </div>

                <h3><span class="control">Corrected</span></h3>
                <ul>
                    <li>Shows only the baseline-corrected subspectrum</li>
                    <li>This is your result after baseline subtraction for this component</li>
                    <li>Baseline points are hidden in this view</li>
                    <li>Interactive baseline editing is not available in this mode</li>
                </ul>

                <div class="screenshot">
                    <img src="$VIEW_CORRECTED" width="$VIEW_CORRECTED_W" height="$VIEW_CORRECTED_H" alt="Corrected view mode" />
                    <p class="caption">Corrected view: only the baseline-subtracted subspectrum is shown.</p>
                </div>

                <h3><span class="control">Both</span></h3>
                <ul>
                    <li>Overlays the original (blue) and corrected (red) subspectrum together</li>
                    <li>Useful for directly comparing before and after correction on the same plot</li>
                    <li>Best view for judging whether a correction removed background without distorting real features</li>
                </ul>

                <div class="screenshot">
                    <img src="$VIEW_BOTH" width="$VIEW_BOTH_W" height="$VIEW_BOTH_H" alt="Both view mode showing original and corrected subspectrum overlaid" />
                    <p class="caption">Both view: original (blue) and corrected (red) subspectrum overlaid for comparison.</p>
                </div>
            </div>
        </div>

        <div class="section">
            <h3>4. Committing Your Correction</h3>
            <div class="method-box">
                <p>Once the baseline corrections and component selection look right — ideally after checking
                <span class="control">Preview Reconstruction</span> and, if you want the numbers behind what you're
                seeing, <span class="control">Diagnostics</span> — use the buttons at the bottom of the dialog
                to commit:</p>
                <ul>
                    <li><span class="control">Apply</span> replaces the spectra loaded in the dialog with their
                    SVD-corrected result. The originals are overwritten once Apply runs.</li>
                    <li><span class="control">Add as New</span> leaves the originals completely untouched and adds
                    the corrected result to the spectra list under new, unique names (e.g.
                    <span class="math">samplename_svd_bg</span>, with a number appended if that name is already
                    taken).</li>
                    <li><span class="control">Close</span> closes the dialog without applying anything to the main
                    window's spectra. Whatever settings were last shown are still remembered the next time the
                    dialog is opened for the same spectra.</li>
                </ul>

                <div class="screenshot">
                    <img src="$COMMIT" width="$COMMIT_W" height="$COMMIT_H" alt="Apply, Add as New, and Close buttons" />
                    <p class="caption">The Help / Apply / Add as New / Close row at the bottom of the dialog.</p>
                </div>
                <p>There is no separate Run step in the main window for this operation — Apply and Add as New
                commit immediately, with their own confirmation message shown right in the dialog, after which
                the dialog closes automatically. Whatever settings were last shown are still remembered the next
                time you reopen it for the same spectra. After a successful commit, any baseline points and
                component inversions are cleared automatically, since they're now baked into the corrected data
                — otherwise they would reappear as stale artefacts the next time you work in this dialog.</p>

                <div class="tip">
                    <strong>Choosing Apply vs. Add as New:</strong> Use <strong>Apply</strong> once you're
                    confident in the correction, to replace your working spectra directly. Use
                    <strong>Add as New</strong> if you want to compare the corrected result side-by-side with the
                    original, or keep iterating on the correction settings on a fresh copy of the dialog.
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Comprehensive Reconstruction Modes</h2>

            <div class="screenshot">
                <img src="$RECON_MODE" width="$RECON_MODE_W" height="$RECON_MODE_H" alt="Reconstruction Mode controls: All, Only corr., First N comp." />
                <p class="caption">All / Only corr. / First N comp. (with its component-count spinner) and the mode's own Help button.</p>
            </div>
            
            <div class="method-box">
                <h3><span class="control">All Subspectra Mode</span></h3>
                <p>This mode uses all computed subspectra for reconstruction, applying any baseline corrections you've made:</p>
                <ul>
                    <li>Provides the most complete reconstruction of your original data</li>
                    <li>Preserves all spectral information while applying baseline corrections</li>
                    <li>Best starting point for most analyses</li>
                    <li>Recommended when you want to remove baseline drift without losing any spectral features</li>
                    <li>Results in spectra that are very similar to originals but with corrected systematic variations</li>
                </ul>
                
                <h3><span class="control">Only Corrected Subspectra Mode</span></h3>
                <p>This aggressive mode uses only subspectra that have baseline corrections applied:</p>
                <ul>
                    <li>Completely removes uncorrected components from the reconstruction</li>
                    <li>Most effective for removing background interferences and systematic variations</li>
                    <li>Can significantly change spectral appearance by removing noise and minor components</li>
                    <li>Only becomes available after you've applied baseline corrections to at least one subspectrum</li>
                    <li>Best for cases where you want maximum background removal</li>
                    <li>May remove some real spectral information if used carelessly</li>
                </ul>
                
                <div class="warning">
                    <strong>Caution with "Only Corrected" Mode:</strong> This mode can be very aggressive. Always preview the results before applying, as it may remove important spectral features if baseline corrections are applied to the wrong components.
                </div>
                
                <h3><span class="control">First N Components Mode</span></h3>
                <p>This mode reconstructs using only the first N components (where N is adjustable):</p>
                <ul>
                    <li>Excellent for noise reduction while preserving main spectral features</li>
                    <li>Use the spinbox to adjust how many components to include (typically 3-10)</li>
                    <li>Removes high-frequency noise and minor systematic variations</li>
                    <li>Any baseline corrections applied to included components are preserved</li>
                    <li>Provides a good balance between noise reduction and feature preservation</li>
                    <li>Ideal when your original spectra are noisy but the main features are in the first few components</li>
                </ul>
                
                <div class="tip">
                    <strong>Choosing N:</strong> Look at the explained variance percentages. Usually, the first 3-5 components explain 90%+ of the variance. Including more components preserves more detail but may include noise.
                </div>
                
                <h3><span class="control">Manual Component Selection</span></h3>
                <p>For maximum flexibility, you can manually select specific components:</p>
                <ul>
                    <li>Uncheck all mode buttons to enable manual selection</li>
                    <li>Use checkboxes in the Selected Components list to choose specific components</li>
                    <li>Allows you to create custom reconstructions by including/excluding specific patterns</li>
                    <li>Most powerful option for experienced users who understand their data structure</li>
                    <li>Useful for removing specific artifacts or systematic effects</li>
                    <li>Requires careful analysis of each component's contribution</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>Detailed Component Information</h2>
            
            <h3>Understanding the Selected Components List</h3>
            <div class="method-box">
                <p>Each component in the list displays three critical values that help you make informed decisions:</p>
                
                <h4><span class="control">Explained Variance Percentage</span></h4>
                <ul>
                    <li>Shows what fraction of total data variance this component represents</li>
                    <li>Displayed with three decimal places for precision (e.g., 98.756%)</li>
                    <li>Components are automatically sorted by variance (highest first)</li>
                    <li>First few components typically explain most of the variance</li>
                    <li>Very low variance components (&lt;0.1%) often represent noise</li>
                </ul>
                
                <h4><span class="control">Singular Value (S)</span></h4>
                <ul>
                    <li>Mathematical magnitude of the component in the SVD decomposition</li>
                    <li>Displayed in scientific notation for easy comparison</li>
                    <li>Directly related to the component's importance in the reconstruction</li>
                    <li>Larger singular values indicate more significant components</li>
                    <li>Useful for determining cutoff points for component inclusion</li>
                </ul>
                
                <h4><span class="control">Residual Error (E)</span></h4>
                <ul>
                    <li>Quality metric based on Malinowski's factor analysis approach</li>
                    <li>Lower values indicate better reconstruction quality for that number of components</li>
                    <li>Helps determine the optimal number of components for reconstruction</li>
                    <li>Useful for identifying where additional components stop adding meaningful information</li>
                </ul>
                
                <div class="tip">
                    <strong>Component Selection Strategy:</strong><br>
                    • <strong>High variance components:</strong> Usually important, examine carefully<br>
                    • <strong>Medium variance components:</strong> May contain systematic effects worth correcting<br>
                    • <strong>Low variance components:</strong> Often noise, but check for systematic patterns<br>
                    • <strong>Very low variance components:</strong> Usually safe to exclude from reconstruction
                </div>
            </div>
            
            <h3>Advanced Component Analysis Tools</h3>
            <div class="method-box">
                <p>Right-click on the Selected Components list to access powerful analysis tools:</p>

                <div class="screenshot">
                    <img src="$COMPONENTS_MENU" width="$COMPONENTS_MENU_W" height="$COMPONENTS_MENU_H" alt="Right-click context menu on the Selected Components list" />
                    <p class="caption">View Singular Values / View Residual Errors / View Singular Values and Residual Errors.</p>
                </div>
                
                <h4><span class="control">View Singular Values</span></h4>
                <ul>
                    <li>Opens a dedicated window showing singular values plotted against component number</li>
                    <li>Available in both linear and logarithmic scales (toggle with radio buttons)</li>
                    <li>Helps identify natural breakpoints in component importance</li>
                    <li>Useful for determining how many components contain significant information</li>
                    <li>Sharp drops in singular values often indicate transition from signal to noise</li>
                </ul>
                
                <h4><span class="control">View Residual Errors</span></h4>
                <ul>
                    <li>Displays residual error plot in a separate window</li>
                    <li>Shows reconstruction quality as a function of number of components included</li>
                    <li>Minimum in the residual error plot indicates optimal number of components</li>
                    <li>Linear and logarithmic scale options available</li>
                    <li>Based on rigorous statistical theory for factor analysis</li>
                </ul>
                
                <h4><span class="control">View Combined Plot</span></h4>
                <ul>
                    <li>Shows both singular values and residual errors in one window</li>
                    <li>Allows easy comparison between component magnitude and reconstruction quality</li>
                    <li>Ideal for making informed decisions about component selection</li>
                    <li>Scale toggle affects both plots simultaneously</li>
                </ul>

                <div class="screenshot">
                    <img src="$SINGULAR_VALUES" width="$SINGULAR_VALUES_W" height="$SINGULAR_VALUES_H" alt="Singular values and residual errors window" />
                    <p class="caption">The combined Singular Values / Residual Errors window, with its Linear/Logarithmic scale toggle.</p>
                </div>
                
                <div class="highlight">
                    <strong>Interpreting the Plots:</strong> Look for "elbows" or sharp changes in the singular values plot, and minima in the residual errors plot. These often indicate the optimal number of components for your analysis.
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Visualization and Interface Controls</h2>
            
            <h3>Plot Context Menu Options</h3>
            <div class="method-box">
                <p>Right-click anywhere on the subspectrum plot area to access these visualization controls:</p>

                <div class="screenshot">
                    <img src="$CANVAS_MENU" width="$CANVAS_MENU_W" height="$CANVAS_MENU_H" alt="Right-click context menu on the subspectrum plot" />
                    <p class="caption">Hide/Show Coefficients Plot, and Show Only SVD Results / Show Controls.</p>
                </div>
                
                <h4><span class="control">Hide/Show Coefficients Plot</span></h4>
                <ul>
                    <li>Toggles the bottom coefficients subplot on and off</li>
                    <li>When hidden, the subspectrum plot expands to fill the entire canvas</li>
                    <li>Useful when you want to focus solely on subspectrum analysis</li>
                    <li>Setting is remembered as you navigate between subspectra</li>
                </ul>
                
                <h4><span class="control">Show Only SVD Results / Show Controls</span></h4>
                <ul>
                    <li>Hides or shows the entire left control panel</li>
                    <li>Maximizes the plot area for detailed subspectrum examination</li>
                    <li>Particularly useful on smaller screens or when presenting results</li>
                    <li>All functionality remains available through keyboard shortcuts when controls are hidden</li>
                </ul>
            </div>
            
            <h3>Preview Reconstruction Feature</h3>
            <div class="method-box">
                <p>The Preview Reconstruction button opens a comprehensive comparison window:</p>
                
                <h4>Preview Window Features:</h4>
                <ul>
                    <li>Side-by-side comparison of original vs reconstructed spectra</li>
                    <li>Select which spectra to display from a multi-select list — click, Ctrl+click, or
                    Shift+click to choose any combination (default: first 5); "Select All" / "Unselect All"
                    buttons are also available</li>
                    <li>Color-coded plots with automatic legend generation</li>
                    <li>Options to link x-axes between top and bottom plots</li>
                    <li>Toggle legend visibility for cleaner plots</li>
                    <li>Full navigation toolbar for detailed examination</li>
                </ul>

                <div class="screenshot">
                    <img src="$PREVIEW_WINDOW" width="$PREVIEW_WINDOW_W" height="$PREVIEW_WINDOW_H" alt="SVD Reconstruction Preview window" />
                    <p class="caption">The Reconstruction Preview window: spectra selection on the left, original vs. reconstructed plots on the right.</p>
                </div>
                
                <h4>Using the Preview Effectively:</h4>
                <ul>
                    <li>Always preview before applying corrections to verify results</li>
                    <li>Compare different reconstruction modes by changing settings and re-previewing</li>
                    <li>Check that important spectral features are preserved</li>
                    <li>Verify that systematic backgrounds have been effectively removed</li>
                    <li>Look for unexpected artifacts or distortions</li>
                </ul>
                
                <div class="tip">
                    <strong>Preview Strategy:</strong> Start with a few representative spectra in the preview. If results look good, you can include more spectra or apply the correction to your full dataset.
                </div>
            </div>

            <h3>Diagnostics Button</h3>
            <div class="method-box">
                <p>Next to <span class="control">Preview Reconstruction</span> is a
                <span class="control">Diagnostics</span> button. Where Preview Reconstruction shows you the
                <em>shape</em> of the correction (the plots), Diagnostics shows you the <em>numbers</em> — a table,
                one row per spectrum, with:</p>
                <ul>
                    <li><strong>Subspectra Used for Reconstruction</strong> and <strong>Baseline Corrected
                    Subspectra</strong> — which components (numbered from 1) actually went into rebuilding this
                    spectrum, and which of those had a baseline correction applied.</li>
                    <li><strong>Original Mean / Corrected Mean</strong> — that spectrum's own average intensity
                    before and after the correction, computed from its own data only.</li>
                    <li><strong>Max Absolute Change</strong> — the single largest point-by-point difference the
                    correction made anywhere in that spectrum.</li>
                    <li><strong>Relative Mean Change</strong> — how much the overall level shifted, as a fraction
                    of the original mean. A large value here can mean the correction removed (or left behind) more
                    background than expected for that particular spectrum — worth a closer look in the plot.</li>
                </ul>
                <div class="note">
                    <strong>Nothing is applied.</strong> Diagnostics computes these values live, from whatever mode
                    and settings are currently active in the dialog — the same computation Apply itself uses, so the
                    numbers you see here are exactly what would be recorded if you clicked Apply right now. Opening
                    it, or changing settings while it's open, never modifies your spectra or their history.
                </div>
                <div class="tip">
                    <strong>Where these numbers go afterward:</strong> once you actually click Apply, this same
                    information — plus a timestamp — is saved into each corrected spectrum's own metadata, under
                    <span class="math">Correction History</span>. Unlike the live Diagnostics table (which only
                    ever shows the current, not-yet-applied settings), that history accumulates: if you run SVD
                    Background on the same spectrum more than once, each application is recorded as its own numbered
                    entry rather than overwriting the last one. This history is also shared with other operations
                    that record one (currently Manual Baseline) — so a spectrum corrected by SVD Background, then
                    Baseline, then SVD Background again shows all three, numbered in the order they actually
                    happened. You can review it any time from that spectrum's Metadata view, without needing to
                    reopen this dialog.
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Advanced Features and Tools</h2>
            
            <h3>Subspectrum Inversion</h3>
            <div class="method-box">
                <p>The Invert button provides a mathematically rigorous way to flip subspectra:</p>
                <ul>
                    <li>Multiplies the subspectrum by -1 (flips it vertically)</li>
                    <li>Automatically adjusts corresponding coefficients to preserve reconstruction accuracy</li>
                    <li>Useful when subspectra appear "upside-down" relative to expected baseline behavior</li>
                    <li>Also inverts any existing baseline points to maintain their relevance</li>
                    <li>The mathematical relationship U×S×V<sup>T</sup> remains unchanged after inversion</li>
                    <li>Can make baseline correction easier by orienting subspectra consistently</li>
                </ul>
                
                <div class="highlight">
                    <strong>Mathematical Note:</strong> Inversion multiplies both U[:,i] and V[i,:] by -1, so their product remains identical. This preserves the reconstruction while making the subspectrum easier to interpret and correct.
                </div>
                
                <div class="warning">
                    <strong>When to Use Inversion:</strong> Only invert subspectra when it makes baseline correction more intuitive. Don't invert subspectra that represent real spectral features, as this can make interpretation more difficult.
                </div>
            </div>
            
            <h3>Baseline Management Tools</h3>
            <div class="method-box">
                <h4><span class="control">Clear Current Baseline</span></h4>
                <ul>
                    <li>Removes all baseline points and corrections for the currently displayed subspectrum</li>
                    <li>Immediately updates the plot to show the original, uncorrected subspectrum</li>
                    <li>Useful for starting over when baseline correction goes wrong</li>
                    <li>Does not affect baseline corrections on other subspectra</li>
                </ul>
                
                <h4><span class="control">Clear All Baselines</span></h4>
                <ul>
                    <li>Removes all baseline corrections from all subspectra (requires confirmation)</li>
                    <li>Resets the entire SVD analysis to its initial state</li>
                    <li>Useful when you want to start the baseline correction process over</li>
                    <li>Cannot be undone, so use with caution</li>
                </ul>

                <div class="screenshot">
                    <img src="$CLEAR" width="$CLEAR_W" height="$CLEAR_H" alt="Clear Baselines: Current and All buttons" />
                    <p class="caption">The Clear Baselines controls: Current and All.</p>
                </div>
                
                <div class="warning">
                    <strong>Clearing Baselines:</strong> These operations cannot be undone. Make sure you're satisfied with your current results before clearing, or use the preview function to save your current settings.
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Comprehensive Best Practices</h2>
            
            <div class="tip">
                <h3>Strategic Component Analysis Approach</h3>
                <ul>
                    <li><strong>Start systematically:</strong> Begin with Component 1 and work through in order of decreasing variance</li>
                    <li><strong>Focus on high-impact components:</strong> The first 3-5 components usually contain most systematic variations worth correcting</li>
                    <li><strong>Identify baseline patterns carefully:</strong> Look for smooth, monotonic curves without sharp spectral features</li>
                    <li><strong>Apply corrections sparingly:</strong> Only correct subspectra that clearly show baseline-like behavior</li>
                    <li><strong>Use preview frequently:</strong> Check results after each major change to ensure you're improving, not degrading, your data</li>
                    <li><strong>Document your approach:</strong> Keep notes on which components you corrected and why</li>
                </ul>
            </div>
            
            <div class="tip">
                <h3>Reconstruction Mode Selection Strategy</h3>
                <ul>
                    <li><strong>Start with "All" mode:</strong> This shows the effect of your baseline corrections while preserving all information</li>
                    <li><strong>Try "First N comp." for noise reduction:</strong> Usually 3-10 components capture the main spectral features</li>
                    <li><strong>Use "Only corr." for aggressive background removal:</strong> But only after carefully validating that corrected components truly represent background</li>
                    <li><strong>Experiment with manual selection:</strong> For advanced users who understand their data structure intimately</li>
                    <li><strong>Always compare modes:</strong> Use the preview function to see how different modes affect your specific dataset</li>
                </ul>
            </div>
            
            <div class="tip">
                <h3>Quality Assessment Guidelines</h3>
                <ul>
                    <li><strong>Check preservation of spectral features:</strong> Important peaks and valleys should remain intact</li>
                    <li><strong>Verify background removal:</strong> Smooth baseline variations should be reduced or eliminated</li>
                    <li><strong>Assess noise levels:</strong> Good SVD correction often reduces noise while preserving signal</li>
                    <li><strong>Compare signal-to-noise ratios:</strong> Corrected spectra should have better S/N in most cases</li>
                    <li><strong>Validate with known standards:</strong> If available, check results against reference spectra</li>
                </ul>
            </div>
            
            <div class="warning">
                <h3>Common Pitfalls and How to Avoid Them</h3>
                <ul>
                    <li><strong>Over-correcting:</strong> Applying baseline correction to subspectra that contain real spectral features - Always examine subspectra carefully before correcting</li>
                    <li><strong>Using too few components:</strong> Removing important spectral information by being too aggressive - Start conservative and gradually become more selective</li>
                    <li><strong>Not checking the preview:</strong> Applying corrections without seeing the final result - Always preview before committing to changes</li>
                    <li><strong>Ignoring component variance:</strong> Spending time correcting very low-variance components that have minimal impact - Focus on components with significant variance first</li>
                    <li><strong>Poor baseline point placement:</strong> Placing baseline points on spectral features rather than true background regions - Study each subspectrum carefully before adding points</li>
                    <li><strong>Inconsistent approach:</strong> Applying different correction strategies to similar components - Develop a systematic approach and stick to it</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>Mathematical Background and Theory</h2>
            
            <h3>Singular Value Decomposition Theory</h3>
            <div class="method-box">
                <div class="equation">
                    <span class="math">A = U × S × V<sup>T</sup></span>
                </div>
                <p>Where each matrix has specific properties and interpretations:</p>
                <ul>
                    <li><span class="math">A</span>: Original data matrix (m×n) where m = number of wavelength points, n = number of spectra</li>
                    <li><span class="math">U</span>: Left singular vectors matrix (m×r) containing subspectra - orthogonal basis functions</li>
                    <li><span class="math">S</span>: Diagonal matrix (r×r) of singular values - indicates component importance</li>
                    <li><span class="math">V<sup>T</sup></span>: Right singular vectors matrix (r×n) containing coefficients - shows component contributions</li>
                    <li><span class="math">r</span>: Rank of the matrix (≤ min(m,n)) - number of independent components</li>
                </ul>
                
                <h4>Mathematical Properties:</h4>
                <ul>
                    <li>U and V are orthogonal matrices: U<sup>T</sup>U = I and V<sup>T</sup>V = I</li>
                    <li>Singular values are non-negative and ordered: s₁ ≥ s₂ ≥ ... ≥ sᵣ ≥ 0</li>
                    <li>Each component contributes: Aᵢ = sᵢ × uᵢ × vᵢ<sup>T</sup></li>
                    <li>Total reconstruction: A = Σᵢ sᵢ × uᵢ × vᵢ<sup>T</sup></li>
                </ul>
            </div>
            
            <h3>Explained Variance Calculation</h3>
            <div class="method-box">
                <div class="equation">
                    <span class="math">Variance<sub>i</sub> = (s<sub>i</sub><sup>2</sup> / Σⱼ s<sub>j</sub><sup>2</sup>) × 100%</span>
                </div>
                <p>This calculation is based on the fundamental relationship between singular values and data variance:</p>
                <ul>
                    <li>Each singular value squared (s²) represents the variance explained by that component</li>
                    <li>The sum of all squared singular values equals the total variance in the data</li>
                    <li>Percentage explained variance shows relative importance of each component</li>
                    <li>Cumulative variance helps determine how many components capture most information</li>
                </ul>
                
                <h4>Interpretation Guidelines:</h4>
                <ul>
                    <li>&gt;50% variance: Dominant component, usually contains main spectral features</li>
                    <li>10-50% variance: Important systematic variation, often worth examining for baseline correction</li>
                    <li>1-10% variance: Minor variations, may represent noise or small systematic effects</li>
                    <li>&lt;1% variance: Usually noise, rarely worth correcting unless very systematic</li>
                </ul>
            </div>
            
            <h3>Residual Error Theory</h3>
            <div class="method-box">
                <div class="equation">
                    <span class="math">E<sub>m</sub> = √[(Σ λ<sub>remaining</sub>) / ((p-m)(n-m))]</span>
                </div>
                <p>Where:</p>
                <ul>
                    <li><span class="math">λ</span> = eigenvalues (s²) of the covariance matrix</li>
                    <li><span class="math">p</span> = number of spectral data points (wavelengths)</li>
                    <li><span class="math">n</span> = number of spectra in the dataset</li>
                    <li><span class="math">m</span> = number of components included in reconstruction</li>
                </ul>
                
                <p>This residual error calculation follows Malinowski's approach for determining the optimal number of factors in chemical data analysis:</p>
                <ul>
                    <li>Based on statistical theory for factor analysis and principal component analysis</li>
                    <li>Accounts for both the unexplained variance and the degrees of freedom</li>
                    <li>Minimum in the error plot indicates statistically optimal number of components</li>
                    <li>Helps distinguish between signal and noise in the SVD decomposition</li>
                    <li>Lower residual errors indicate better reconstruction quality for that number of components</li>
                </ul>
                
                <h4>Practical Application:</h4>
                <ul>
                    <li>Plot residual error vs number of components to find the "elbow" or minimum</li>
                    <li>The minimum often corresponds to the optimal balance between fit and overfitting</li>
                    <li>Components beyond the minimum typically represent noise</li>
                    <li>Use this information to guide component selection for reconstruction</li>
                </ul>
            </div>
            
            <h3>Baseline Correction Mathematics</h3>
            <div class="method-box">
                <p>When baseline correction is applied to subspectra, the mathematical operations are:</p>
                
                <h4>For Spline Fitting:</h4>
                <div class="equation">
                    <span class="math">B(x) = CubicSpline(x<sub>points</sub>, y<sub>points</sub>)</span>
                </div>
                <ul>
                    <li>Uses cubic spline interpolation through user-defined baseline points</li>
                    <li>Provides smooth, continuous baseline with continuous first and second derivatives</li>
                    <li>Automatically handles varying point spacing</li>
                    <li>Extrapolates linearly beyond the range of baseline points</li>
                </ul>
                
                <h4>For Polynomial Fitting:</h4>
                <div class="equation">
                    <span class="math">B(x) = Σᵢ aᵢ × x<sup>i</sup></span>
                </div>
                <ul>
                    <li>Fits polynomial of specified degree through baseline points using least squares</li>
                    <li>Degree is automatically limited by number of points (n points → max degree n-1)</li>
                    <li>Higher degrees can capture more complex baseline shapes but may overfit</li>
                    <li>Provides analytical mathematical form for the baseline</li>
                </ul>
                
                <h4>Corrected Subspectrum:</h4>
                <div class="equation">
                    <span class="math">U'<sub>corrected</sub> = U<sub>original</sub> - B(x)</span>
                </div>
                <p>The baseline-corrected subspectrum is used in place of the original for reconstruction, preserving the mathematical structure of the SVD while removing systematic baseline variations.</p>
            </div>
        </div>

        <div class="section">
            <h2>Comprehensive Troubleshooting Guide</h2>
            
            <div class="method-box">
                <h3>SVD Computation Issues</h3>
                
                <h4>Problem: SVD Computation Fails</h4>
                <ul>
                    <li><strong>Check x-axis consistency:</strong> All spectra must have identical wavelength/wavenumber points</li>
                    <li><strong>Verify data format:</strong> Ensure all y-values are numerical (not NaN or infinite)</li>
                    <li><strong>Confirm minimum dataset size:</strong> Need at least 2 spectra for meaningful SVD</li>
                    <li><strong>Check memory availability:</strong> Very large datasets may exceed available RAM</li>
                    <li><strong>Validate data ranges:</strong> Extremely large or small values may cause numerical issues</li>
                </ul>
                
                <h4>Problem: Poor Component Separation</h4>
                <ul>
                    <li><strong>Insufficient spectral diversity:</strong> Very similar spectra produce less meaningful components</li>
                    <li><strong>Dominated by noise:</strong> High noise levels can obscure systematic variations</li>
                    <li><strong>Limited systematic variation:</strong> If no systematic effects present, SVD may not be beneficial</li>
                    <li><strong>Preprocessing needed:</strong> Consider smoothing or other preprocessing before SVD</li>
                </ul>
            </div>
            
            <div class="method-box">
                <h3>Baseline Correction Problems</h3>
                
                <h4>Problem: Cannot Add Baseline Points</h4>
                <ul>
                    <li><strong>Check baseline mode:</strong> Ensure "On" is selected in baseline correction settings</li>
                    <li><strong>Verify view mode:</strong> Must be in "Original" view mode, not "Corrected"</li>
                    <li><strong>Confirm plot focus:</strong> Click on the plot area to ensure it has focus</li>
                    <li><strong>Check click location:</strong> Must left-click directly on the subspectrum curve</li>
                    <li><strong>Zoom level issues:</strong> Try zooming out if the plot seems unresponsive</li>
                </ul>
                
                <h4>Problem: Baseline Points Won't Remove</h4>
                <ul>
                    <li><strong>Right-click technique:</strong> Must right-click near (not on) the baseline point</li>
                    <li><strong>Tolerance issues:</strong> Try clicking closer to the point you want to remove</li>
                    <li><strong>Multiple points:</strong> If points are very close, try zooming in for precision</li>
                    <li><strong>Plot refresh:</strong> Sometimes switching subspectra and back helps refresh the display</li>
                </ul>
                
                <h4>Problem: Strange Baseline Shapes</h4>
                <ul>
                    <li><strong>Too few points:</strong> Need at least 2 points, more for complex shapes</li>
                    <li><strong>Poor point placement:</strong> Points should represent true baseline, not spectral features</li>
                    <li><strong>High polynomial order:</strong> Reduce polynomial degree if using polynomial fitting</li>
                    <li><strong>Outlier points:</strong> Remove points that don't fit the expected baseline pattern</li>
                    <li><strong>Switch fitting method:</strong> Try spline if polynomial gives poor results, or vice versa</li>
                </ul>
            </div>
            
            <div class="method-box">
                <h3>Reconstruction and Results Issues</h3>
                
                <h4>Problem: Reconstruction Looks Wrong</h4>
                <ul>
                    <li><strong>Check component selection:</strong> Verify which components are included in reconstruction</li>
                    <li><strong>Review baseline corrections:</strong> Ensure corrections were applied to appropriate components</li>
                    <li><strong>Try different modes:</strong> Compare "All", "Only corr.", and "First N" modes</li>
                    <li><strong>Use preview function:</strong> Always preview before applying to see intermediate results</li>
                    <li><strong>Examine individual components:</strong> Check that corrected components make sense</li>
                </ul>
                
                <h4>Problem: Lost Spectral Features</h4>
                <ul>
                    <li><strong>Over-aggressive correction:</strong> May have corrected components containing real spectral information</li>
                    <li><strong>Too few components:</strong> Try including more components in reconstruction</li>
                    <li><strong>Wrong reconstruction mode:</strong> "Only corr." mode can be too aggressive for some datasets</li>
                    <li><strong>Review component analysis:</strong> Re-examine which components truly represent baseline vs features</li>
                </ul>
                
                <h4>Problem: Insufficient Background Removal</h4>
                <ul>
                    <li><strong>Missed components:</strong> May need to apply baseline correction to additional components</li>
                    <li><strong>Poor baseline fitting:</strong> Add more baseline points or adjust fitting parameters</li>
                    <li><strong>Try more aggressive mode:</strong> Consider "Only corr." mode if background persists</li>
                    <li><strong>Check for systematic patterns:</strong> Look for baseline-like behavior in higher-numbered components</li>
                </ul>
            </div>
            
            <div class="method-box">
                <h3>Performance and Interface Issues</h3>
                
                <h4>Problem: Slow Performance</h4>
                <ul>
                    <li><strong>Large dataset:</strong> SVD computation time scales with dataset size</li>
                    <li><strong>Memory limitations:</strong> Close other applications to free RAM</li>
                    <li><strong>Plot rendering:</strong> Hide coefficients plot if not needed to improve responsiveness</li>
                    <li><strong>Reduce preview spectra:</strong> Show fewer spectra in preview window</li>
                </ul>
                
                <h4>Problem: Interface Responsiveness</h4>
                <ul>
                    <li><strong>Plot focus issues:</strong> Click on plot area to ensure proper focus for mouse events</li>
                    <li><strong>Update delays:</strong> Allow time for complex calculations to complete</li>
                    <li><strong>Screen resolution:</strong> Adjust window size for optimal display on your monitor</li>
                    <li><strong>Hide panels:</strong> Use context menu to hide panels and maximize plot area</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>References and Further Reading</h2>
            <div class="method-box">
                <h3>Primary Mathematical References</h3>
                <ul>
                    <li><strong>Golub, G.H. & Van Loan, C.F.</strong> "Matrix Computations, 4th Edition" (Johns Hopkins University Press, 2013) - Comprehensive treatment of SVD theory and computational methods</li>
                    <li><strong>Jolliffe, I.T.</strong> "Principal Component Analysis, 2nd Edition" (Springer, 2002) - Statistical foundations and practical applications of PCA/SVD</li>
                    <li><strong>Malinowski, E.R.</strong> "Factor Analysis in Chemistry, 3rd Edition" (Wiley, 2002) - Chemical applications of factor analysis and SVD methods</li>
                </ul>
                
                <h3>Spectroscopic Applications</h3>
                <ul>
                    <li><strong>Bro, R. & Smilde, A.K.</strong> "Principal component analysis" (Analytical Methods, 2014) - Modern perspective on PCA applications</li>
                </ul>
                
                <h3>Implementation and Computational Aspects</h3>
                <ul>
                    <li><strong>For residual error calculation:</strong> The implementation is following Malinowski's statistical approach for determining optimal factor numbers</li>
                    <li><strong>NumPy SVD documentation:</strong> Technical details of the SVD implementation used in this software</li>
                    <li><strong>SciPy spline interpolation:</strong> Mathematical basis for the cubic spline baseline fitting method</li>
                </ul>
                
                <h3>Practical Guidance</h3>
                <ul>
                    <li><strong>Jackson, J.E.</strong> "A User's Guide to Principal Components" (Wiley, 2003) - Accessible introduction to PCA theory and practice</li>
                    <li><strong>Brereton, R.G.</strong> "Chemometrics: Data Analysis for the Laboratory and Chemical Plant" (Wiley, 2003) - Applications in analytical chemistry</li>
                </ul>
                
                <h3>Application to Raman Spectroscopy of Aqueous Solutions</h3>
                <ul>
                    <li><strong>Palack&yacute;, J., Mojze&scaron;, P., &amp; Bok, J. (2011).</strong>
                    &ldquo;SVD-based method for intensity normalization, background correction and
                    solvent subtraction in Raman spectroscopy exploiting the properties of water
                    stretching vibrations.&rdquo;
                    <em>Journal of Raman Spectroscopy</em>, <strong>42</strong>(7), 1528&ndash;1539.
                    <a href="https://doi.org/10.1002/jrs.2896">https://doi.org/10.1002/jrs.2896</a><br>
                    <em>Describes the application of SVD decomposition for simultaneous intensity
                    normalisation, water background correction, and solvent subtraction in
                    Raman spectra of aqueous biological samples &mdash; the methodological
                    basis for the SVD background correction implemented in this software.</em>
                    </li>
                </ul>

                <h3>Software and Implementation</h3>
                <ul>
                    <li><strong>Python Scientific Computing:</strong> NumPy, SciPy, and Matplotlib libraries provide the computational foundation</li>
                    <li><strong>PyQt5 Documentation:</strong> User interface framework for the interactive components</li>
                    <li><strong>Matplotlib Documentation:</strong> Plotting and visualization capabilities</li>
                </ul>
                
                <div class="highlight">
                    <strong>Note on Implementation:</strong> This software implements SVD background correction using industry-standard numerical libraries (NumPy) with algorithms based on well-established mathematical principles. The residual error calculation specifically follows Malinowski's approach.
                </div>
            </div>
        </div>
    </body>
    </html>""")

    return help_template.safe_substitute(images)


def get_svd_background_help_title():
    """
    Get the title for the SVD background correction help window.
    
    Returns:
        str: Window title
    """
    return "SVD Background Correction - Help"