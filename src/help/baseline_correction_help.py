# src/help/baseline_correction_help.py

"""
Help content for manual baseline correction functionality.
This module contains detailed help information that can be reused across the application.
"""

import os
import struct
from pathlib import Path
from string import Template

# NOTE: adjust this import to match wherever resource_path() actually lives
# in your project. baseline_correction_dialog.py imports its sibling
# app_logger from src.modules.utils, so that's the path assumed here —
# change it if resource_path.py lives somewhere else.
from src.modules.utils.resource_path import resource_path


# Screenshots referenced by this help page. Keep the PNGs here, and
# resource_path() will resolve them correctly both when running from source
# and when running from a PyInstaller-frozen build.
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "manual_baseline")

_SCREENSHOT_FILES = {
    "OVERVIEW":       "dialog_overview.png",
    "ENABLE":         "enable_baseline_correction.png",
    "POINTS_ADDED":   "baseline_points_added.png",
    "FITTING":        "baseline_fitting_methods.png",
    "COMMIT":         "commit_buttons.png",
    "VIEW_ORIGINAL":  "view_mode_original.png",
    "VIEW_CORRECTED": "view_mode_corrected.png",
    "VIEW_BOTH":      "view_mode_both.png",
    "CLEAR":          "clear_baselines_buttons.png",
    "SUMMARY_TABLE":  "correction_summary_table.png",
    "CONTEXT_MENU":   "context_menu_show_only_spectrum.png",
}

# Cap displayed screenshot width at this many pixels. Qt's rich-text engine
# (what show_help_window renders into) doesn't reliably honor CSS
# "max-width: 100%" on <img> the way a real browser does, so a screenshot
# saved at its native size (e.g. a 1900px-wide capture) shows up at full
# native size and forces a horizontal scrollbar. Setting explicit width/
# height attributes (computed below, aspect ratio preserved) is what
# actually constrains it in Qt. Tune this to comfortably fit your help
# window's content area (window width minus body margin/padding).
_MAX_IMG_WIDTH = 700


def _png_size(path):
    """
    Return (width, height) in pixels for a PNG, read straight from its
    IHDR chunk — avoids needing Pillow just to check dimensions.
    """
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
    preserved) so every <img> tag renders at a sane, consistent size instead
    of at the screenshot's raw captured resolution.
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
            # Screenshot missing/unreadable when the help page is built
            # (e.g. a fresh checkout without the images yet) — fall back to
            # a fixed box instead of crashing the whole help page.
            display_w, display_h = _MAX_IMG_WIDTH, round(_MAX_IMG_WIDTH * 0.6)

        values[f"{key}_W"] = str(display_w)
        values[f"{key}_H"] = str(display_h)

    return values


def get_baseline_correction_help_content():
    """
    Get the HTML help content for manual baseline correction.

    Returns:
        str: HTML formatted help content
    """

    images = _resolve_screenshot_uris()

    # Using string.Template ($NAME placeholders) instead of str.format()/f-strings
    # on purpose: the CSS block below is full of literal { } braces, which would
    # collide with .format()-style placeholders.
    help_template = Template("""
    <!DOCTYPE html>
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
            .shortcut { font-family: monospace; background-color: #ecf0f1; padding: 2px 5px; border-radius: 3px; }
            ul { margin-left: 20px; }
            li { margin-bottom: 5px; }
            .method-box { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>
        <h1>Manual Baseline Correction Help</h1>
        
        <div class="section">
            <h2>Overview</h2>
            <p>Manual baseline correction allows you to interactively remove baseline drift from individual spectra by defining baseline points and fitting curves through them. This method gives you precise control over the baseline correction process for each spectrum.</p>
            
            <div class="highlight">
                <strong>Key Concept:</strong> You manually select points on the spectrum that represent the baseline (background), and the software fits a curve through these points. The baseline is then subtracted from the original spectrum.
            </div>
        </div>

        <div class="section">
            <h2>Interface Layout</h2>

            <div class="screenshot">
                <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="Manual Baseline Correction dialog overview" />
                <p class="caption">The full dialog: spectrum navigation and settings on the left, the interactive plot on the right.</p>
            </div>
            
            <h3>Left Panel - Controls</h3>
            <ul>
                <li><span class="control">Spectra List:</span> Shows all selected spectra. Click to switch between spectra. Use the sort button (▲/▼) to change sorting order.</li>
                <li><span class="control">Baseline Correction Settings:</span> Configure correction parameters</li>
                <li><span class="control">View Mode Controls:</span> Choose what to display</li>
                <li><span class="control">Clear Baselines:</span> Reset corrections</li>
            </ul>
            
            <h3>Right Panel - Interactive Plot</h3>
            <ul>
                <li>Main spectrum display with interactive baseline editing</li>
                <li>Navigation toolbar for zooming and panning</li>
                <li>Coordinate display showing current mouse position</li>
            </ul>
        </div>

        <div class="section">
            <h2>Step-by-Step Workflow</h2>
            
            <h3>1. Enable Baseline Correction</h3>
            <div class="method-box">
                <ul>
                    <li>Ensure <span class="control">"On"</span> is selected in the "Enable Baseline Correction" section</li>
                    <li>The plot should show your spectrum in blue</li>
                    <li>Mouse clicks are now enabled for baseline point placement</li>
                </ul>

                <div class="screenshot">
                    <img src="$ENABLE" width="$ENABLE_W" height="$ENABLE_H" alt="Enable Baseline Correction On/Off control" />
                    <p class="caption">The Enable Baseline Correction control, with "On" selected.</p>
                </div>
            </div>
            
            <h3>2. Add Baseline Points</h3>
            <div class="method-box">
                <ul>
                    <li><strong>Left-click</strong> on the spectrum to add baseline points (green circles)</li>
                    <li>Place points where you believe the baseline should be (typically in valleys or flat regions)</li>
                    <li>You need at least 2 points to generate a baseline</li>
                    <li>Add more points for better baseline accuracy</li>
                </ul>

                <div class="screenshot">
                    <img src="$POINTS_ADDED" width="$POINTS_ADDED_W" height="$POINTS_ADDED_H" alt="Baseline points placed on a spectrum" />
                    <p class="caption">Baseline points (green circles) placed in valleys between spectral features.</p>
                </div>
                
                <div class="tip">
                    <strong>Tip:</strong> Place baseline points strategically in regions without spectral features, such as valleys between peaks or flat background regions.
                </div>
            </div>
            
            <h3>3. Remove Baseline Points</h3>
            <div class="method-box">
                <ul>
                    <li><strong>Right-click</strong> near any green baseline point to remove it</li>
                    <li>The software automatically finds the nearest point within tolerance</li>
                    <li>Baseline curve updates automatically after point removal</li>
                </ul>
            </div>
            
            <h3>4. Configure Baseline Fitting</h3>
            <div class="method-box">
                <h4>Fitting Methods:</h4>
                <ul>
                    <li><span class="control">Spline:</span> Smooth cubic spline interpolation (default, recommended)</li>
                    <li><span class="control">Poly:</span> Polynomial fitting with adjustable order</li>
                </ul>
                
                <h4>Polynomial Order:</h4>
                <ul>
                    <li>Only available when "Poly" is selected</li>
                    <li>Higher orders create more flexible curves but may overfit</li>
                    <li>Typical range: 2-6</li>
                </ul>

                <div class="screenshot">
                    <img src="$FITTING" width="$FITTING_W" height="$FITTING_H" alt="Baseline Fitting controls: Spline, Poly, and Polynomial Order" />
                    <p class="caption">Spline vs. Poly fitting, with the Polynomial Order spinner enabled only for Poly.</p>
                </div>
            </div>

            <h3>5. Commit Your Correction</h3>
            <div class="method-box">
                <p>Once the baseline points and fitting method look right for the spectra you want to
                correct, use the buttons at the bottom of the dialog to commit:</p>
                <ul>
                    <li><span class="control">Apply</span> replaces the spectra loaded in the dialog with
                    their baseline-corrected result. Spectra with no baseline points defined are left
                    untouched. The originals are overwritten once Apply runs.</li>
                    <li><span class="control">Add as New</span> leaves the originals completely untouched
                    and adds the corrected result to the spectra list under new, unique names (e.g.
                    <span class="shortcut">samplename_baseline</span>, with a number appended if that name
                    is already taken). Only spectra that actually had baseline points defined are added.</li>
                    <li><span class="control">Close</span> closes the dialog without applying anything to
                    the main window's spectra.</li>
                </ul>

                <div class="screenshot">
                    <img src="$COMMIT" width="$COMMIT_W" height="$COMMIT_H" alt="Apply, Add as New, and Close buttons" />
                    <p class="caption">The Apply, Add as New, and Close buttons at the bottom of the dialog.</p>
                </div>

                <p>There is no separate Run step in the main window for this operation — Apply and Add as
                New commit immediately, with their own confirmation message shown right in the dialog,
                after which the dialog closes automatically. After a successful commit, baseline points
                are cleared automatically, since they're now baked into the corrected data — otherwise
                they would reappear as stale artefacts the next time you work in this dialog.</p>
                <div class="tip">
                    <strong>Tip:</strong> Use <strong>Apply</strong> once you're confident in the
                    correction, to replace your working spectra directly. Use <strong>Add as New</strong>
                    if you want to compare the corrected result side-by-side with the original.
                </div>
            </div>
        </div>

        <div class="section">
            <h2>View Modes</h2>
            
            <div class="method-box">
                <h3><span class="control">Original</span></h3>
                <ul>
                    <li>Shows original spectrum (blue) with baseline points (green) and baseline curve (green dashed)</li>
                    <li>Use this mode for placing and adjusting baseline points</li>
                </ul>

                <div class="screenshot">
                    <img src="$VIEW_ORIGINAL" width="$VIEW_ORIGINAL_W" height="$VIEW_ORIGINAL_H" alt="Original view mode" />
                    <p class="caption">Original view: spectrum (blue), baseline points (green), baseline curve (green dashed).</p>
                </div>
                
                <h3><span class="control">Corrected</span></h3>
                <ul>
                    <li>Shows only the baseline-corrected spectrum (red)</li>
                    <li>This is your final result after baseline subtraction</li>
                    <li>Baseline points are hidden in this view</li>
                    <li>Interactive baseline editing is not available in this mode</li>
                </ul>

                <div class="screenshot">
                    <img src="$VIEW_CORRECTED" width="$VIEW_CORRECTED_W" height="$VIEW_CORRECTED_H" alt="Corrected view mode" />
                    <p class="caption">Corrected view: only the baseline-subtracted spectrum (red) is shown.</p>
                </div>
                
                <h3><span class="control">Both</span></h3>
                <ul>
                    <li>Shows original (blue), baseline curve (green dashed), and corrected (red) spectra</li>
                    <li>Useful for comparing before and after correction</li>
                    <li>Baseline points are visible for reference</li>
                </ul>

                <div class="screenshot">
                    <img src="$VIEW_BOTH" width="$VIEW_BOTH_W" height="$VIEW_BOTH_H" alt="Both view mode" />
                    <p class="caption">Both view: original (blue), baseline (green dashed), and corrected (red) together.</p>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Control Functions</h2>
            
            <h3>Clear Baselines</h3>
            <div class="method-box">
                <ul>
                    <li><span class="control">Current:</span> Removes all baseline points and correction for the currently displayed spectrum</li>
                    <li><span class="control">All:</span> Removes all baseline corrections for all spectra (requires confirmation)</li>
                    <li><span class="control">Summary:</span> Shows a table summarizing all applied baseline corrections</li>
                </ul>

                <div class="screenshot">
                    <img src="$CLEAR" width="$CLEAR_W" height="$CLEAR_H" alt="Clear Baselines: Current, All, Summary buttons" />
                    <p class="caption">The Clear Baselines controls: Current, All, and Summary.</p>
                </div>

                <div class="screenshot">
                    <img src="$SUMMARY_TABLE" width="$SUMMARY_TABLE_W" height="$SUMMARY_TABLE_H" alt="Baseline correction summary table" />
                    <p class="caption">The Summary dialog: spectrum, point count, fit type, and polynomial order for every correction.</p>
                </div>
            </div>
            
            <h3>Context Menu Options</h3>
            <div class="method-box">
                <p>Right-click on the plot area (not on a baseline point) to access:</p>
                <ul>
                    <li><span class="control">Show Only Spectrum:</span> Hides the left control panel for maximum plot area</li>
                    <li><span class="control">Show Controls:</span> Restores the control panel visibility</li>
                </ul>

                <div class="screenshot">
                    <img src="$CONTEXT_MENU" width="$CONTEXT_MENU_W" height="$CONTEXT_MENU_H" alt="Right-click context menu on the plot" />
                    <p class="caption">Right-clicking empty plot area shows the Show Only Spectrum / Show Controls option.</p>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Best Practices</h2>
            
            <div class="tip">
                <h3>Baseline Point Placement</h3>
                <ul>
                    <li>Place points in regions without spectral features</li>
                    <li>Use sufficient points to capture baseline curvature</li>
                    <li>Avoid placing points on peak shoulders or in noisy regions</li>
                    <li>Start with fewer points and add more as needed</li>
                </ul>
            </div>
            
            <div class="tip">
                <h3>Method Selection</h3>
                <ul>
                    <li><strong>Spline fitting:</strong> Best for most cases, provides smooth baselines</li>
                    <li><strong>Polynomial fitting:</strong> Use when you need specific mathematical forms</li>
                    <li>Start with spline fitting and switch to polynomial only if needed</li>
                </ul>
            </div>
            
            <div class="warning">
                <h3>Common Pitfalls</h3>
                <ul>
                    <li>Placing baseline points on or near spectral peaks</li>
                    <li>Using too high polynomial orders (causes overfitting)</li>
                    <li>Not having enough baseline points to capture baseline shape</li>
                    <li>Forgetting to check the corrected spectrum in "Both" or "Corrected" view</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>Technical Details</h2>
            
            <h3>Spline Fitting</h3>
            <div class="method-box">
                <ul>
                    <li>Uses cubic spline interpolation for smooth baseline curves</li>
                    <li>Automatically handles varying point spacing</li>
                    <li>Provides natural-looking baseline shapes</li>
                    <li>Requires minimum 2 points (linear interpolation for 2 points)</li>
                </ul>
            </div>
            
            <h3>Polynomial Fitting</h3>
            <div class="method-box">
                <ul>
                    <li>Fits polynomial of specified order through baseline points</li>
                    <li>Order is automatically limited by number of points (n points = max order n-1)</li>
                    <li>Higher orders can capture complex baseline shapes but may oscillate</li>
                    <li>Uses least-squares fitting for optimal curve placement</li>
                </ul>
            </div>
            
            <h3>Auto-Save Functionality</h3>
            <div class="highlight">
                <p>All baseline corrections are automatically saved as you work. Changes are immediately stored when you:</p>
                <ul>
                    <li>Add or remove baseline points</li>
                    <li>Change fitting method or polynomial order</li>
                    <li>Switch between spectra</li>
                </ul>
            </div>
        </div>

        <div class="section">
            <h2>Troubleshooting</h2>
            
            <div class="method-box">
                <h3>Cannot Add Baseline Points</h3>
                <ul>
                    <li>Ensure "On" is selected in "Enable Baseline Correction"</li>
                    <li>Make sure you're in "Original" or "Both" view mode</li>
                    <li>Check that you're left-clicking directly on the spectrum</li>
                </ul>
                
                <h3>Baseline Doesn't Update</h3>
                <ul>
                    <li>You need at least 2 baseline points for curve generation</li>
                    <li>Check that points are properly placed (look for green circles)</li>
                    <li>Try switching view modes to refresh the display</li>
                </ul>
                
                <h3>Strange Baseline Shape</h3>
                <ul>
                    <li>Remove poorly placed baseline points</li>
                    <li>Reduce polynomial order if using polynomial fitting</li>
                    <li>Switch to spline fitting for smoother results</li>
                    <li>Add more strategically placed baseline points</li>
                </ul>
            </div>
        </div>
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


def get_baseline_correction_help_title():
    """
    Get the title for the baseline correction help window.
    
    Returns:
        str: Window title
    """
    return "Manual Baseline Correction - Help"
