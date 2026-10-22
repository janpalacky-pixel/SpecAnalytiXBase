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
    markers and labels on top of whatever's currently plotted.</p>
    <p><b>Right-click on the plot &rarr; Detect Peaks</b> opens the Peak Detection Settings.
    <b>Apply</b> marks the peaks with the settings shown and the window stays open, so you can
    change a setting and Apply again until the result fits; <b>Close</b> closes the window
    (settings changed after the last Apply are not used). <b>Reset to defaults</b> puts every
    setting back to its default value. The orange <b>?</b> shows what each setting means; the
    same text appears when you hold the mouse over a setting.</p>

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
    <p>Defaults: threshold 0.5, prominence 0.1, distance 0.05, Positive; font size 10,
    rotation 0, 2 decimal places, fixed point, x value only.</p>

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
    <h2 id="peak-list">Peak list</h2>
    <p><b>Right-click on the plot &rarr; Peak list&hellip;</b> (or the <b>Peak list&hellip;</b> button
    in the Peak Detection Settings) lists every peak of <b>all selected spectra</b> in one table
    &mdash; also of spectra a large selection does not draw. The peaks are found by exactly the same
    rule and settings as the markers on the plot; change the settings in the list and the table
    follows at once (Detect Peaks then uses them too). Columns:</p>
    <ul>
        <li><b>Peak</b>: its number within the spectrum, from low to high x; <b>Kind</b>: maximum
            or minimum.</li>
        <li><b>Position (x)</b> and <b>Height (y)</b>: of the highest (or lowest) measured point
            &mdash; so the position is as precise as the point spacing. For a position between the
            points, use Peak Fitting.</li>
        <li><b>Prominence</b>: how far the peak stands out from its surroundings.</li>
        <li><b>FWHM</b>: the width at half of the prominence, and where it starts and ends
            (<b>Left / Right half-height x</b>), interpolated between the points (also for uneven
            point spacing). Overlapping bands make it a rough estimate.</li>
    </ul>
    <p>Click a heading to sort by it. Select rows and press Ctrl+C (or <b>Copy</b>) to paste them
    into Excel with the column names; <b>Export&hellip;</b> saves the list as Excel or CSV.
    <b>Reset to defaults</b> and the orange <b>?</b> work as in the Peak Detection Settings (the
    <b>?</b> also explains the columns).</p>
    <h3 id="peak-plot">Plot</h3>
    <p>The tab <b>Plot</b> draws one number of the peaks against another:</p>
    <ul>
        <li><b>x</b>: a value of the spectrum &mdash; its order in the list, a value stored with it
            (e.g. <code>temperature_C</code> of a JASCO temperature scan) or a number in its name
            (only values that differ between the spectra are offered) &mdash; or a number of the peak itself: position, height, prominence, FWHM or the
            peak number (1st, 2nd, &hellip; peak of its spectrum; e.g. the position against the peak
            number shows how much the 1st, 2nd, &hellip; peak varies between the spectra);</li>
        <li><b>x = Peak by its position</b>: each peak at the position of its band &mdash; peaks
            of different spectra closer than <b>same peak within &plusmn;</b> (in x units; set from
            the widths of the peaks, half of the median FWHM) are the same band and get one common
            position (their median), so a band measured at 685 in one spectrum and 686 in the next
            is one column. <b>As labels</b> puts the bands side by side with their positions as
            names (e.g. 686, 1093); <b>on the x scale</b> puts them at their positions. A peak
            that is missing in some spectra (not found there) is not invented: its band simply has
            no point for those spectra, and the other bands keep their place &mdash; unlike the
            peak number, where the peaks after a missing one move up by one (the 2nd becomes the
            1st, &hellip;). A band that shifts gradually through a series stays one band as long
            as its neighbouring positions are within the &plusmn; distance; two bands closer than it
            become one (then lower it). Unlike <b>Position (x)</b>, all spectra share the band's
            position;</li>
        <li><b>y</b>: position, height, prominence or FWHM.</li>
    </ul>
    <p>For example the position against the temperature shows how a band shifts through a
    melting series, and the height against the position shows which bands are strong. The
    points are coloured by the <b>peak number</b> (1st, 2nd, &hellip; peak of each spectrum from
    low to high x), by <b>maximum / minimum</b>, or in one colour. <b>Join the same peak
    number</b> draws lines through the 1st peak of each spectrum, the 2nd peak of each, &hellip;,
    each line in its own colour (named in the legend). With x a value of the spectrum the line
    runs along x; with x a number of the peak (e.g. the height) it runs from spectrum to spectrum
    in the order of the list. It is greyed out when x is the peak itself (its number or its
    position), where the points of one peak lie above each other. <b>Legend</b> shows or hides
    the legend. The peak numbers count from
    low x, so when a peak appears or disappears in some spectra the numbers after it shift: to
    follow one band, sort the table by position, select its rows and tick <b>Only the selected
    rows</b>. <b>Copy plot</b> puts the plot on the clipboard for Word or PowerPoint; the toolbar
    zooms and saves it.</p>

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
