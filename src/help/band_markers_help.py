# src/help/band_markers_help.py

"""
Help content for the Band Markers dialog.
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
_SCREENSHOT_DIR = os.path.join("resources", "images", "help_screenshots", "band_markers")

_SCREENSHOT_FILES = {
    "OVERVIEW":       "dialog_overview.png",
    "SINGLE_EDIT":    "single_row_edit.png",
    "BULK_EDIT":      "bulk_edit.png",
    "PLOT_EXAMPLE":   "markers_on_plot.png",
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


def get_band_markers_help_title():
    """Return the title for Band Markers help."""
    return "Band Markers — Help"


def get_band_markers_help_content():
    """
    Get the HTML help content for the Band Markers dialog.

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
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
            .fm   { font-family: monospace; background: #ececec;
                    padding: 1px 5px; border-radius: 3px; }
            .screenshot { margin: 12px 0; text-align: center; }
            .screenshot img { border: 1px solid #dee2e6; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
            .screenshot .caption { font-size: 0.9em; color: #7f8c8d; font-style: italic; margin-top: 6px; }
        </style>
    </head>
    <body>

    <h1>Band Markers</h1>

    <p>Band Markers are named reference lines drawn on top of every plot —
    useful for marking known band positions, thresholds, or anything else
    worth calling out on the spectra you're looking at. They're drawn on
    <em>all</em> plot modes simultaneously (overlay, grid, waterfall, mean
    &plusmn; SD, difference, heatmap) and persist for the whole session, not
    just the current plot.</p>

    <div class="screenshot">
        <img src="$OVERVIEW" width="$OVERVIEW_W" height="$OVERVIEW_H" alt="Band Markers dialog overview" />
        <p class="caption">The Band Markers dialog: the global toggle and label-offset-from-line control at the top, the marker table in the middle (with its own per-marker Label offset column), and the Add/Edit row at the bottom.</p>
    </div>

    <div class="note">
        <strong>Two kinds of marker:</strong> every marker is either an
        <strong>X marker</strong> — a vertical line at a constant x, marking
        an x-value (e.g. a band position) — or a <strong>Y marker</strong> — a
        horizontal line at a constant y, marking a y-value (e.g. a
        threshold). Set independently per marker via its <strong>Axis</strong>
        column / control.
    </div>

    <div class="screenshot">
        <img src="$PLOT_EXAMPLE" width="$PLOT_EXAMPLE_W" height="$PLOT_EXAMPLE_H" alt="An X marker and a Y marker shown together on a spectrum plot" />
        <p class="caption">An X marker (vertical line, marking a band position) and a Y marker (horizontal line, marking a threshold) shown together on the same plot.</p>
    </div>

    <hr>
    <h2>Opening the dialog</h2>
    <p>Click <strong>Band markers&hellip;</strong> in the Basic plot options
    panel to open the Band Marker Manager.</p>

    <hr>
    <h2>Adding a marker</h2>
    <p>Fill in the row at the bottom of the dialog and click <strong>Add</strong>:</p>
    <table>
        <tr><th>Field</th><th>Meaning</th></tr>
        <tr><td><strong>Position</strong></td><td>The x-value (for an X marker)
            or y-value (for a Y marker). A plain text field rather than a
            spinbox on purpose — this same field holds typical x-values
            (hundreds to thousands) for X markers and small y-values (e.g.
            0.0001 to 0.002) for Y markers, and a fixed decimal count can't
            represent both well. Accepts any precision, including scientific
            notation (e.g. <span class="fm">5e-4</span>).</td></tr>
        <tr><td><strong>Axis</strong></td><td><em>X (vertical line)</em> or
            <em>Y (horizontal line)</em> — see above.</td></tr>
        <tr><td><strong>Label</strong></td><td>The text shown next to the
            line, e.g. <em>Phe 1004</em>. Leave blank and the marker's
            position becomes its label automatically.</td></tr>
        <tr><td><strong>Style</strong></td><td>Line style: Dashed (--),
            Solid (-), Dotted (:), or Dash-dot (-.).</td></tr>
        <tr><td><strong>Width</strong></td><td>Line width.</td></tr>
        <tr><td><strong>Font size</strong></td><td>Size of the label text, in
            points.</td></tr>
        <tr><td><strong>Label offset</strong></td><td>How far down from the
            top of the plot this marker's label starts, as a percentage
            (0&ndash;100%) of the y-axis range (for a Y marker, measured from
            the right edge instead, by symmetry). 0% starts right at the
            edge; 100% pushes it all the way to the opposite edge. Per
            marker, so different markers can use different offsets — e.g.
            to stack labels at different heights when several sit close
            together. Increase it if a label overlaps a top tick number or
            exponent.</td></tr>
        <tr><td><strong>Label dir</strong></td><td><em>Vertical</em> (the
            default) reads bottom-to-top alongside the line and takes almost
            no space along the line; <em>Horizontal</em> is easier to read
            but takes more room and can run into a neighbouring marker if two
            are close together. Independent of Axis — any combination of the
            two is valid.</td></tr>
        <tr><td><strong>Color&hellip;</strong></td><td>Opens the color
            picker for the line and label together.</td></tr>
    </table>

    <hr>
    <h2>Editing markers</h2>
    <p>Existing markers can be edited three ways, kept in sync with each
    other:</p>

    <h3>1. Inline, directly in the table</h3>
    <p>Double-click a cell. Position, Label, Width, Font size, and Label
    offset open the normal in-place text editor — type a new value and press
    Enter. Axis, Line style, Label dir, Color, and Visible aren't plain text,
    so they open their own small picker instead (a menu, the color dialog,
    or — for Visible — a direct toggle).</p>

    <h3>2. Single-row edit, via the bottom row</h3>
    <div class="screenshot">
        <img src="$SINGLE_EDIT" width="$SINGLE_EDIT_W" height="$SINGLE_EDIT_H" alt="A single row selected, with Update selected and Cancel edit buttons showing" />
        <p class="caption">Selecting one row loads it into the bottom row and turns Add into Update selected.</p>
    </div>
    <p>Select exactly one row — it loads its Position / Axis / Label / Style
    / Width / Font size / Label offset / Label dir / Color into the bottom
    row, and <strong>Add</strong> becomes <strong>Update selected</strong>.
    Adjust whatever needs changing and click Update — it applies all of them
    to that marker at once, and the marker <em>stays selected</em>
    afterward, so a second or third tweak doesn't need reselecting it from
    the table again. <strong>Cancel edit</strong> discards the change and
    returns to adding a new marker instead.</p>

    <h3>3. Bulk edit, for several markers at once</h3>
    <div class="screenshot">
        <img src="$BULK_EDIT" width="$BULK_EDIT_W" height="$BULK_EDIT_H" alt="Several rows selected at once, with the Update N selected button showing" />
        <p class="caption">Selecting 2 or more rows (Ctrl+click, or drag) loads a bulk edit instead — Position and Label are disabled, everything else applies to the whole batch.</p>
    </div>
    <p>Select 2 or more rows (Ctrl+click, or drag) to load Style, Width, Font
    size, Label offset, Label dir, Color, and Axis into the bottom row —
    seeded from the first selected marker — and the button becomes
    <strong>Update N selected</strong>. <strong>Position and Label are
    disabled</strong> in this mode: setting several different markers to the
    identical position or label text wouldn't make sense. Adjust whichever of
    the remaining fields should apply to the whole batch and click Update —
    it's applied to every selected marker at once, which then stays selected
    afterward for a further tweak, the same way single-row editing does.</p>

    <div class="tip">
        <strong>Selection is resilient by design:</strong> if the table's
        selection ever transiently drops to nothing while you're mid-edit —
        for instance from interacting with the bottom row's own fields — the
        dialog actively re-selects whatever you were editing rather than
        silently discarding it. Use <strong>Cancel edit</strong> to explicitly
        abandon an in-progress edit instead of clicking around the table.
    </div>

    <hr>
    <h2>Removing markers</h2>
    <p><strong>Remove selected</strong> deletes whichever row(s) are
    currently selected (one or several); <strong>Clear all</strong> deletes
    every marker.</p>

    <hr>
    <h2>Visibility</h2>
    <p>Two independent levels of control:</p>
    <ul>
        <li>The <strong>Show all band markers on plots</strong> checkbox,
            top-left, hides or shows <em>every</em> marker at once, without
            deleting any of them.</li>
        <li>Each marker also has its own <strong>Visible</strong> column —
            double-click it to toggle just that one marker, independent of
            the global checkbox.</li>
    </ul>

    <hr>
    <h2>Label placement</h2>
    <p>Two things fine-tune where a label sits relative to its own line and
    to the edge of the plot — useful when a label collides with the line
    itself, or with a y-axis tick number / scientific-notation exponent near
    the top of the plot:</p>
    <ul>
        <li><strong>Label offset</strong> (per marker — see the Adding a
            marker table above, and the Label offset column) sets how far
            down from the top of the plot <em>that specific marker's</em>
            label starts. Since it's set individually, different markers can
            use different offsets — for instance, stacking two markers'
            labels at different heights when they sit close together on the
            axis so their labels don't overlap each other.</li>
        <li><strong>Label offset from line</strong>, top-right of the
            dialog, is the one setting that's still shared by every marker:
            the gap, in points, between a marker's line and the start of its
            label. Increase it if a line crosses through its own label's
            characters.</li>
    </ul>

    <hr>
    <h2>Elsewhere</h2>
    <div class="tip">
        Band markers also appear in external figure windows opened via
        right-click &rarr; Open in New Window — they're not specific to the
        main plot canvas.
    </div>

    </body>
    </html>
    """)

    return help_template.safe_substitute(images)
