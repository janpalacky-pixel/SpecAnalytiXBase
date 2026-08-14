# src/help/peak_detection_help.py

def get_peak_detection_help_title():
    return "Peak Detection — Help"

def get_peak_detection_help_content():
    return """
    <html><head><style>
        body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
        h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
        h2    { color: #1565C0; margin-top: 22px; }
        .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        .note { background: #E3F2FD; border-left: 4px solid #1565C0; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        table { border-collapse: collapse; width: 100%; margin: 8px 0; }
        th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
        td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
        ul,ol { padding-left: 20px; } li { margin: 3px 0; }
        hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        .fm   { font-family: monospace; background: #ececec; padding: 1px 5px; border-radius: 3px; }
    </style></head><body>

    <h1>Peak Detection</h1>

    <p>Peak Detection marks local maxima or minima directly on the current
    plot — a quick visual aid, not a data-modifying operation. It doesn't
    change your spectra or save anything to their metadata; it just draws
    markers and labels on top of whatever's currently plotted. Reopen the
    dialog and click Detect again any time to update or clear the markers.</p>

    <div class="note">
        This is different from <strong>Peak Fitting</strong>, which models
        peaks mathematically (Gaussian/Lorentzian) and can save fitted
        parameters to a spectrum's metadata. Use Peak Detection for a quick
        visual survey of a plot; use Peak Fitting when you need quantitative
        peak parameters (center, height, FWHM, area).
    </div>

    <hr>
    <h2>Parameters</h2>
    <table>
        <tr><th>Parameter</th><th>Meaning</th></tr>
        <tr><td><strong>Peak Detection Threshold</strong></td>
            <td>Minimum height, as a fraction (0&ndash;1) of each line's own
            intensity range, a point must reach before it's even considered
            as a candidate peak.</td></tr>
        <tr><td><strong>Prominence Threshold (Relative)</strong></td>
            <td>How much a candidate peak must stand out from its
            surrounding baseline, as a fraction of the line's intensity
            range. Raise this to ignore small bumps riding on a larger
            feature.</td></tr>
        <tr><td><strong>Distance Threshold (Relative)</strong></td>
            <td>Minimum spacing between detected peaks, as a fraction of the
            number of points in the line. Raise this to avoid multiple
            markers crowding around what's really one broad peak.</td></tr>
        <tr><td><strong>Peak Detection Mode</strong></td>
            <td><em>Positive</em> finds local maxima (upward peaks),
            <em>Negative</em> finds local minima (downward dips/troughs),
            <em>Both</em> finds both at once.</td></tr>
        <tr><td><strong>Peak Value Font Size / Text Rotation / Decimal
            Places / Number Format / Display Format</strong></td>
            <td>Purely cosmetic — control how (and whether) each marker's
            coordinates are labeled on the plot.</td></tr>
    </table>

    <hr>
    <h2>How detection works</h2>
    <p>Each plotted line is analyzed independently. For <em>Negative</em>
    mode, the line's y-values are inverted first, then searched the same
    way <em>Positive</em> mode searches the original — so a "negative peak"
    is really a local minimum (a downward-pointing dip) in your data.</p>
    <p>All three thresholds are computed from each line's own data — a
    threshold of 0.5, for instance, always means "half of this particular
    line's own range," not a fixed absolute value — so the same settings
    can be reused sensibly across lines with very different intensity
    scales.</p>

    <hr>
    <h2>Clearing markers</h2>
    <p>Detecting again automatically clears the previous markers first, so
    re-running with different settings never leaves stale markers behind
    or double-counts them as data on a later detection.</p>

    <div class="tip">
        <strong>Tip:</strong> if a real, obvious dip or peak isn't being
        picked up, try lowering the Prominence or Distance threshold before
        the main Threshold — prominence and distance are usually what's
        filtering it out, not the height threshold itself.
    </div>

    </body></html>
    """
