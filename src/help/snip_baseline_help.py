# src/help/snip_baseline_help.py

def get_snip_baseline_help_title():
    return 'SNIP Baseline Correction — Help'

def get_snip_baseline_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note { background: #E3F2FD; border-left: 4px solid #1565C0;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn { background: #FFF8E1; border-left: 4px solid #F9A825;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm   { font-family: monospace; background: #ececec;
                    padding: 1px 5px; border-radius: 3px; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        </style>
    </head>
    <body>

    <h1>SNIP Baseline Correction</h1>

    <p>SNIP (Statistics-sensitive Non-linear Iterative Peak-clipping) is a
    parameter-light automatic baseline estimator that works by iteratively
    clipping the signal downward until only slowly-varying background remains.
    It requires no manual anchor points and produces a smooth, physically
    plausible baseline for most fluorescence backgrounds encountered in
    Raman and X-ray fluorescence spectroscopy.</p>

    <div class="note">
        <strong>Typical pipeline position:</strong><br>
        Data range &rarr; Spike removal &rarr; <strong>SNIP baseline</strong>
        &rarr; Smoothing &rarr; Normalization &rarr; further analysis.<br>
        Apply SNIP before smoothing so that the baseline estimator works on the
        raw signal shape. Run spike removal first to avoid spikes being
        incorporated into the baseline estimate.
    </div>

    <hr>
    <h2>Algorithm</h2>

    <p>The algorithm operates in three stages:</p>

    <h3>1 — Variance-stabilising transform (optional)</h3>
    <p>
        <span class="fm">z = sqrt(y + 3/8)</span><br>
        Converts Poisson shot noise (variance &prop; signal) into approximately
        uniform variance. This makes the clipping threshold statistically
        consistent across the full spectral range. Recommended for
        Raman and XRF spectra. Uncheck for data that is already linearised
        or log-scaled.
    </p>

    <h3>2 — Iterative peak clipping</h3>
    <p>For each iteration <em>m</em> (window half-width), every point is
    replaced by the minimum of itself and the average of its two neighbours
    at distance <em>m</em>:</p>
    <p style="margin-left:16px">
        <span class="fm">z[i] = min(z[i],&nbsp; (z[i&minus;m] + z[i+m]) / 2)</span>
    </p>
    <p>Broad peaks are clipped away because they rise above the local average
    of their neighbours. Slowly-varying background is preserved because it
    satisfies the average condition. With <em>decreasing window order</em>
    (recommended), <em>m</em> runs from <em>n_iter</em> down to 1, giving a
    smoother and more conservative result.</p>

    <h3>3 — Back-transform and clip</h3>
    <p>If the transform was applied:
        <span class="fm">baseline = z&sup2; &minus; 3/8</span>.
    The result is clipped so the baseline never exceeds the original signal.
    </p>

    <hr>
    <h2>Parameters</h2>

    <table>
        <tr><th>Parameter</th><th>Effect</th><th>Typical value</th></tr>
        <tr>
            <td><strong>Iterations</strong></td>
            <td>Controls how wide a feature can be and still be clipped away.
                More iterations &rarr; wider baseline, broader features removed.
                Too many iterations may clip broad Raman bands along with the
                fluorescence background.</td>
            <td>50&ndash;200 for Raman fluorescence.
                Start at 100 and adjust while watching the preview.</td>
        </tr>
        <tr>
            <td><strong>Decreasing window order</strong></td>
            <td>Processes windows from large to small rather than small to large.
                Produces a smoother, more conservative baseline.
                Almost always preferable &mdash; leave checked.</td>
            <td>On (recommended)</td>
        </tr>
        <tr>
            <td><strong>Variance-stabilising transform (&radic;)</strong></td>
            <td>Applies <span class="fm">sqrt(y + 3/8)</span> before clipping.
                Equalises the statistical weight of high- and low-intensity
                regions. Recommended for shot-noise-limited data.</td>
            <td>On for Raman / XRF; off for log-scale or pre-processed data</td>
        </tr>
        <tr>
            <td><strong>Pre-smooth half-window</strong></td>
            <td>Applies a moving average of width <em>2w + 1</em> before
                the SNIP algorithm runs. Reduces the effect of high-frequency
                noise on the baseline estimate. Set to 0 (off) unless the
                signal has very high noise.</td>
            <td>0 (off) in most cases; 1&ndash;3 for very noisy data</td>
        </tr>
    </table>

    <hr>
    <h2>Preview</h2>

    <p>The preview updates automatically as you adjust parameters (250&nbsp;ms
    debounce). Use the <strong>◀ / ▶</strong> navigator or click an entry in
    the spectra list to switch between spectra.</p>

    <table>
        <tr><th>View mode</th><th>Shows</th></tr>
        <tr>
            <td><strong>Subplots</strong></td>
            <td>Original + baseline overlay (top) and corrected result (bottom),
                shared x-axis. Best for seeing exactly where the baseline sits
                relative to the signal.</td>
        </tr>
        <tr>
            <td><strong>Overlay</strong></td>
            <td>Original (blue), baseline (orange dashed), and corrected (green)
                on one axes. Useful for comparing absolute levels.</td>
        </tr>
    </table>

    <hr>
    <h2>Committing your correction</h2>

    <p>Once the parameters look right in the preview, use the buttons at the bottom of the dialog
    to commit:</p>
    <ul>
        <li><strong>Apply</strong> replaces the spectra loaded in the dialog with their
        baseline-corrected result. The originals are overwritten once Apply runs.</li>
        <li><strong>Add as New</strong> leaves the originals completely untouched and adds the
        corrected result to the spectra list under new, unique names (e.g.
        <span class="fm">samplename_baseline_snip</span>, with a number appended if that name is
        already taken).</li>
        <li><strong>Close</strong> closes the dialog without applying anything to the main
        window's spectra.</li>
    </ul>
    <p>There is no separate Run step in the main window for this operation — Apply and Add as New
    commit immediately, with their own confirmation message shown right in the dialog, after which
    the dialog closes automatically. Whatever settings were last shown are still remembered the
    next time you reopen it for the same spectra.</p>

    <hr>
    <h2>Practical tips</h2>

    <div class="tip">
        <strong>Start with the default settings</strong> (100 iterations,
        decreasing order, transform on). For most Raman fluorescence backgrounds
        the defaults give a good result immediately. Increase iterations if the
        baseline still follows spectral peaks; decrease if it dips below the
        baseline in flat regions.
    </div>

    <div class="tip">
        <strong>Watch the corrected panel, not just the baseline.</strong>
        A good SNIP result has a flat, near-zero corrected spectrum in
        peak-free regions and preserves peak heights and shapes. If corrected
        peaks are clipped at the top, the iteration count is too high.
    </div>

    <div class="warn">
        <strong>SNIP is best for smooth, slowly-varying backgrounds.</strong>
        For sharp backgrounds, highly structured fluorescence, or spectra
        where bands overlap the baseline region, manual baseline correction
        or SVD background may give better results.
    </div>

    <div class="warn">
        <strong>Very broad peaks can be mistaken for baseline</strong> if the
        iteration count is high relative to the peak width in data points.
        If a broad Raman band is being partially removed, reduce the iteration
        count or switch to manual baseline correction for that region.
    </div>

    <hr>
    <h2>Reference</h2>

    <p>Ryan, C.G., Clayton, E., Griffin, W.L., Sie, S.H., Cousens, D.R.
    (1988). &ldquo;SNIP, a statistics-sensitive background treatment for
    the quantitative analysis of PIXE spectra in geoscience
    applications.&rdquo; <em>Nuclear Instruments and Methods in Physics
    Research B</em>, <strong>34</strong>(3), 396&ndash;402.</p>

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
    """
