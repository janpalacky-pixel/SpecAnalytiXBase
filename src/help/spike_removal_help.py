# src/help/spike_removal_help.py

def get_spike_removal_help_title():
    return "Spike Removal — Help"

def get_spike_removal_help_content():
    return """
    <html><head><style>
        body  { font-family: Arial, sans-serif; margin: 16px; line-height: 1.55; font-size: 13px; }
        h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
        h2    { color: #1565C0; margin-top: 18px; }
        h3    { color: #E65100; margin-top: 12px; margin-bottom: 3px; }
        .cat  { background: #f5f5f5; padding: 9px 13px; margin: 5px 0; border-radius: 5px; }
        .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32; padding: 8px 12px; margin: 7px 0; }
        .warn { background: #FFF3E0; border-left: 4px solid #E65100; padding: 10px 14px;
                border-radius: 3px; margin: 10px 0; }
        .ref  { background: #f9f9f9; border: 1px solid #ddd; padding: 9px 13px;
                border-radius: 3px; margin: 8px 0; font-style: italic; }
        .fm   { font-family: monospace; background: #ececec; padding: 1px 4px; border-radius: 3px; }
        ul,ol { padding-left: 18px; } li { margin: 3px 0; }
        hr    { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
        table { border-collapse: collapse; width: 100%; }
        th    { background: #E3F2FD; text-align: left; padding: 5px 7px; }
        td    { border-bottom: 1px solid #e0e0e0; padding: 4px 7px; }
    </style></head><body>

    <h1>Spike Removal</h1>

    <p>Spikes are narrow, sharp artefacts caused by cosmic rays hitting the detector.
    They appear as one or a few points with abnormally high (or occasionally low)
    intensity, unrelated to the sample spectrum. This dialog lets you detect them
    automatically and review each one interactively before committing the removal.</p>

    <hr>
    <h2>Detection algorithm</h2>

    <div class="cat">
        <h3>Modified Z-score on the 2nd derivative</h3>
        <p>Based on <b>Whitaker &amp; Hayes (2018)</b>.</p>
        <p>The <b>second derivative</b> is computed first:</p>
        <p style="margin-left:16px">
            <span class="fm">d²y[i] = y[i+1] − 2·y[i] + y[i−1]</span>
        </p>
        <p>A spike has a very large |d²y[i]| because it deviates sharply from both
        neighbours, while broad spectral bands produce small d²y values.</p>
        <p>The <b>modified Z-score</b> is then computed:</p>
        <p style="margin-left:16px">
            <span class="fm">Z[i] = 0.6745 × (d²y[i] − median(d²y)) / MAD(d²y)</span>
        </p>
        <p>where MAD = median absolute deviation. Using median and MAD (not mean and
        standard deviation) makes the score robust to the very spikes being detected.
        A point is classified as a spike if |Z[i]| &gt; threshold.</p>
        <p><b>Marker placement:</b> the raw d&sup2;y score identifies a candidate
        index that is not always the visual tip of the spike. On a steep slope
        (e.g. the descending edge of a Raman band) the equal-and-opposite
        &ldquo;rebound&rdquo; lobe of d&sup2;y one point after the tip can dominate,
        placing the marker at the spike base rather than its peak. The algorithm
        therefore snaps each candidate to the point of largest absolute deviation
        from the local median within &plusmn;half-window, ensuring the marker lands
        on the true spike tip. Nearby candidates within half-window of each other
        are merged into the one with the largest deviation.</p>

        <p><b>Replacement:</b> detected spike pixels are replaced by linear interpolation
        between the nearest clean neighbours on each side.</p>
    </div>

    <hr>
    <h2>Parameters</h2>

    <div class="cat">
        <h3>Threshold</h3>
        <p>The |Z| value above which a point is classified as a spike.
        Lower = more aggressive (more detections). Higher = more conservative
        (only very prominent spikes). Typical range: 5–15. Default: 7.</p>
    </div>

    <div class="cat">
        <h3>Half-window</h3>
        <p>Number of points on each side of the spike centre to include in the
        replacement region. Default: 2 (replacing 5 points total). Increase if
        spikes in your data are wider than 2–3 points.</p>
        <p>Replacement formula for each spike pixel i:</p>
        <p style="margin-left:16px">
            <span class="fm">y_new[i] = y[left] + (i − left) / (right − left) × (y[right] − y[left])</span>
        </p>
        <p>where left and right are the nearest clean points outside the spike window.</p>
    </div>

    <hr>
    <h2>Workflow</h2>
    <ol>
        <li>Set global <b>Threshold</b> and <b>Half-window</b>, then click
            <b>Re-detect all spectra</b>.</li>
        <li>Navigate through spectra using the list or <b>Prev / Next</b> buttons.</li>
        <li>For any spectrum where the global threshold gives poor results, adjust
            the parameters in <b>This spectrum — override</b> and click
            <b>Re-detect this spectrum</b>. Spectra with a custom threshold show
            an asterisk (*) in the list.</li>
        <li>Enable <b>Show data points</b> to see exact point positions before
            clicking — especially useful when spikes are close together.</li>
        <li>Enable <b>Spike editing mode</b> (orange button) to interactively
            modify the detections on the current spectrum.</li>
        <li>Left-click any orange ▲ marker to remove it from the removal list.
            Left-click empty spectrum space to add a manual spike at that point.</li>
        <li>Click <b>Apply</b> to replace the selected spectra with the despiked result, or
            <b>Add as New</b> to keep the originals untouched and add the result under new names.</li>
    </ol>

    <div class="tip">
        <b>Apply vs. Add as New vs. Close:</b>
        <ul>
            <li><b>Apply</b> replaces the spectra loaded in the dialog with their despiked
                result. The originals are overwritten once Apply runs.</li>
            <li><b>Add as New</b> leaves the originals completely untouched and adds the
                despiked result to the spectra list under new, unique names (e.g.
                <span class="fm">samplename_despiked</span>, with a number appended if that
                name is already taken).</li>
            <li><b>Close</b> closes the dialog without applying anything to the main window's
                spectra. Whatever spikes were marked are still remembered the next time you
                reopen it for the same spectra &mdash; unless a different operation (e.g. a
                baseline correction) is applied to one of those spectra in the meantime, in
                which case its marks are cleared automatically, since they no longer describe
                the spectrum's current data.</li>
        </ul>
        <p>There is no separate Run step in the main window for this operation — Apply and
        Add as New commit immediately, with their own confirmation message shown right in the
        dialog, after which the dialog closes automatically.</p>
    </div>

    <div class="warn">
        <b>&#9888; Important:</b> Turn <b>OFF</b> spike editing mode before zooming
        or panning — otherwise every click adds a spike marker. Turn it <b>ON only
        when you want to mark or remove spikes</b>.<br><br>
        The zoom is preserved between edits so you can mark multiple spikes in the
        same zoomed region without re-zooming. Use the toolbar <b>Home</b> button
        (&#x2302;) to return to the full view.
    </div>

    <hr>
    <h2>Interactive editing controls</h2>
    <table>
        <tr><th>Action</th><th>Result</th></tr>
        <tr><td>Enable Spike editing mode</td>
            <td>Clicking the canvas marks/removes spikes (zoom preserved)</td></tr>
        <tr><td>Left-click orange ▲ marker</td>
            <td>Remove this spike from the removal list (it disappears)</td></tr>
        <tr><td>Left-click empty spectrum point</td>
            <td>Add a manual spike at that position (orange ▲)</td></tr>
        <tr><td>Show data points checkbox</td>
            <td>Overlay small circles on each data point — helps click precisely</td></tr>
        <tr><td>Re-detect this spectrum</td>
            <td>Re-run detection for current spectrum only with custom parameters</td></tr>
        <tr><td>Re-detect all spectra</td>
            <td>Re-run detection for all spectra; clears all manual edits</td></tr>
        <tr><td>Toolbar Home button (&#x2302;)</td>
            <td>Restore full unzoomed view</td></tr>
    </table>

    <div class="tip">
        <b>Marker legend:</b> Orange ▲ = will be removed.
        All markers behave identically regardless of whether they were auto-detected
        or manually added — left-click removes them from the removal list.
    </div>

    <hr>
    <h2>Reference</h2>
    <div class="ref">
        <b>Whitaker, D.A. &amp; Hayes, K. (2018).</b>
        "A simple algorithm for despiking Raman spectra."
        <i>Chemometrics and Intelligent Laboratory Systems</i> <b>179</b>, 82–84.
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

    </body></html>
    """
