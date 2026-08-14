# src/help/cosmic_ray_help.py

def get_cosmic_ray_help_title():
    return 'Cosmic Ray Detection (cross-spectrum) — Help'

def get_cosmic_ray_help_content():
    return """
    <html><head><style>
        body  { font-family:Arial,sans-serif; margin:20px; line-height:1.6; font-size:13px; }
        h1    { color:#2E7D32; border-bottom:2px solid #2E7D32; }
        h2    { color:#1565C0; margin-top:22px; }
        .tip  { background:#E8F5E9; border-left:4px solid #2E7D32; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .note { background:#E3F2FD; border-left:4px solid #1565C0; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .warn { background:#FFF8E1; border-left:4px solid #F9A825; padding:10px 14px; border-radius:3px; margin:8px 0; }
        table { border-collapse:collapse; width:100%; margin:8px 0; }
        th    { background:#E3F2FD; text-align:left; padding:6px 8px; }
        td    { border-bottom:1px solid #e0e0e0; padding:5px 8px; vertical-align:top; }
        ul,ol { padding-left:20px; } li { margin:3px 0; }
        hr    { border:none; border-top:1px solid #ddd; margin:20px 0; }
        .fm   { font-family:monospace; background:#ececec; padding:1px 5px; border-radius:3px; }
    </style></head><body>

    <h1>Cosmic Ray Detection (cross-spectrum)</h1>

    <p>Cosmic rays are high-energy particles that cause sharp, intense spikes
    in CCD-based spectrometers. Unlike shot noise, a cosmic ray typically
    affects only a single pixel (or a few pixels) in a single spectrum of a
    replicate series — the same pixel in all other spectra is unaffected.</p>

    <div class="note">
        <strong>Difference from single-spectrum spike removal:</strong>
        The existing Spike Removal tool detects spikes by looking at the
        second derivative within each spectrum. This works well for narrow
        spikes but can fail for broader rays or spectra with high noise.
        Cross-spectrum detection is more reliable for replicate series because
        it compares each point against the same wavenumber position across all
        spectra.
    </div>

    <div style="background:#FFEBEE; border-left:5px solid #C62828; padding:12px 16px; border-radius:3px; margin:12px 0;">
        <strong style="color:#C62828; font-size:14px;">&#9888; Critical assumption</strong><br><br>
        This method assumes that <strong>any large intensity difference at the
        same wavenumber position across spectra is a cosmic ray, not a real
        spectral feature.</strong> It flags any point that is statistically
        anomalous relative to the group median as a cosmic ray.<br><br>
        <strong>This assumption is only valid when all selected spectra are
        replicates</strong> &mdash; measurements of the same or very similar
        samples where the spectra should look broadly identical.
        <strong>If your spectra are from genuinely different samples
        (different concentrations, different tissues, different compounds),
        the method will incorrectly flag real spectral differences as
        cosmic rays. This will corrupt your data.</strong><br><br>
        <strong>Do NOT use this method when:</strong>
        <ul style="margin:6px 0;">
            <li>Spectra come from <strong>different samples</strong> (different
                tissues, different compounds, different concentrations) &mdash;
                real spectral differences will be incorrectly flagged as cosmic rays.</li>
            <li>Spectra are from a <strong>concentration series</strong> or
                <strong>time series</strong> with systematic intensity changes.</li>
            <li>You have <strong>fewer than ~30 spectra</strong> &mdash; the
                group median is not robust with small groups and legitimate
                outlier spectra (e.g. slightly different focus) will be
                incorrectly flagged. The dialog shows a warning in this case.
                Use single-spectrum Spike Removal instead.</li>
        </ul>
        <strong>Always inspect the preview</strong> (Summary &amp; Preview tab) before
        applying removal to visually confirm that flagged points are genuine
        cosmic rays (narrow isolated spikes) and not real spectral features.
    </div>

    <div class="note">
        <strong>All selected spectra must share the same x-axis.</strong>
        This method compares every spectrum against the others at each
        x-position, so there's no valid way to compare spectra that were
        never measured at the same points. If your spectra don't already
        share an axis, this operation refuses to run and tells you which
        spectrum differs — use the <em>Data Range</em> operation (with
        linearisation) to put every spectrum on a common axis first.
    </div>

    <hr>
    <h2>Algorithm</h2>
    <ol>
        <li>Confirm every selected spectrum shares the same x-axis (refuses
            with a clear message if not — see above).</li>
        <li>For each x-position, compute the <strong>median</strong> and
            <strong>MAD</strong> (median absolute deviation) across all spectra.</li>
        <li>Compute the modified Z-score for each (spectrum, x-position) pair:
            <br><span class="fm">Z(i,j) = 0.6745 &times; (y[i,j] &minus; median[j]) / MAD[j]</span></li>
        <li>Flag any point where |Z| &gt; threshold — this cross-spectrum
            comparison is what finds broad rays or rays in noisy spectra that
            single-spectrum Spike Removal can miss.</li>
        <li>Each flagged point, plus <strong>Replace window</strong> extra
            points on each side, is replaced by linear interpolation between
            the nearest <em>un</em>-replaced points in that <em>same</em>
            spectrum's own trace — not the group median used for detection.
            Replacement never depends on the other spectra's values, only on
            this spectrum's own real data on either side of the corrected
            region, so it can't be thrown off by another spectrum's own noise
            or an overlapping cosmic ray elsewhere in the group.</li>
    </ol>

    <hr>
    <h2>Threshold</h2>
    <p>The threshold controls sensitivity:</p>
    <ul>
        <li><strong>Lower (5&ndash;8):</strong> more sensitive — catches
            weaker rays but may flag legitimate spectral variation between
            samples.</li>
        <li><strong>Higher (10&ndash;20):</strong> less sensitive — only
            flags very strong outliers. Recommended default: 10.</li>
        <li><strong>Very high (&gt;20):</strong> only extremely intense
            rays are flagged.</li>
    </ul>

    <div class="cat">
        <h3>Replace window (extra points on each side)</h3>
        <p>The flagged point itself is <em>always</em> replaced — this setting
        only controls how many <em>extra</em> points on each side also get
        replaced along with it. A cosmic ray's shoulders are often still
        visibly elevated without being anomalous enough to be individually
        flagged, which can leave a small remnant right where the ray was if
        only the exact flagged point is corrected.</p>
        <ul>
            <li><strong>0</strong> — replace only the flagged point(s), no
                buffer on either side. Can leave visible shoulder remnants.</li>
            <li><strong>1&ndash;2 (recommended, default: 1)</strong> — also
                smooths over those shoulders without eating into real
                spectral features nearby.</li>
        </ul>
        <p>Use <strong>Corrected only</strong> preview mode (below) to check
        for remnants before committing, and increase this if you still see
        them.</p>
    </div>

    <div class="warn" style="border-color:#C62828; background:#FFEBEE;">
        <strong style="color:#C62828;">Minimum recommended group size: 30+ spectra.</strong>
        With fewer spectra, the group median used for <em>detection</em> is
        less stable and legitimate intensity variation between spectra is
        more likely to be flagged. The dialog shows a warning when fewer
        than 30 spectra are selected. With very few spectra (e.g. 5&ndash;14),
        use the single-spectrum Spike Removal instead.
    </div>

    <hr>
    <h2>Outlier heatmap</h2>
    <p>The heatmap shows |Z-score| at every (spectrum, x-position) pair.
    Bright regions indicate outliers. The cyan contour line marks the
    threshold boundary — points above it will be flagged.</p>
    <p>Use the heatmap to visually confirm that flagged regions correspond
    to real cosmic rays (narrow vertical bright streaks in one spectrum)
    rather than legitimate spectral differences (broad bright regions
    across many spectra).</p>

    <hr>
    <h2>Summary &amp; Preview</h2>
    <p>This is the tab shown by default when the dialog opens, since it's
    what you need first — which spectra were flagged, and what the
    correction looks like. It combines a few things so you don't have to
    switch back and forth:</p>
    <ul>
        <li><strong>Summary table (left):</strong> lists each spectrum, how many points
            were flagged, and the x-positions of flagged points (first 10 shown). <em>Show
            only spectra with flagged points</em> is ticked by default, and the first
            flagged spectrum is selected automatically so the preview isn't left blank.</li>
        <li><strong>Preview mode (right):</strong> three options —
            <ul>
                <li><strong>Original only</strong> — the spectrum as-is, with flagged
                    points marked in red.</li>
                <li><strong>Original + Corrected</strong> — both overlaid, so you can see
                    exactly what changed.</li>
                <li><strong>Corrected only</strong> — just the corrected result. With the
                    original also shown, a sharp spike's extreme value stretches the whole
                    plot's y-axis to fit it, flattening everything else and making it hard
                    to judge how clean the correction actually looks — dropping the
                    original lets the axis rescale to the corrected data's own range
                    instead, which is usually the more useful view for checking quality.</li>
            </ul>
            Click any row in the table to preview that spectrum — updates immediately
            without leaving the tab, and reflects the current Replace window setting live,
            without applying anything.</li>
    </ul>

    <hr>
    <h2>Applying removal</h2>
    <ul>
        <li><strong>Apply</strong> replaces the selected spectra with their cosmic-ray-corrected
            result. The originals are overwritten
            once Apply runs.</li>
        <li><strong>Add as New</strong> leaves the originals completely untouched and adds the
            corrected result to the spectra list under new, unique names (e.g.
            <span class="fm">samplename_cosmic_ray</span>, with a number appended if that name is
            already taken).</li>
        <li><strong>Close</strong> closes the dialog without applying anything to the main
            window's spectra. Whatever threshold was last shown is still remembered the next
            time you reopen it for the same spectra.</li>
    </ul>
    <p>There is no separate Run step in the main window for this operation — Apply and Add as
    New commit immediately, with their own confirmation message shown right in the dialog,
    after which the dialog closes automatically.</p>
    <p>Only spectra that actually had a point replaced are affected — if you select 500 spectra
    and only 12 have cosmic rays, Apply/Add as New only touch those 12; the other 488 are left
    completely alone, and Operations History's affected-spectra list only lists those 12 as well.</p>
    <p>Applying to a selection with many affected spectra can take a moment — a progress
    indicator is shown while it runs.</p>

    <div class="note">
        <strong>Metadata record:</strong> each corrected spectrum's own metadata gets a
        <span class="fm">Correction History</span> entry (tagged <span class="fm">Cosmic Ray
        Removal</span>, with a timestamp, the threshold and Replace window used, and the
        flagged x-positions) — viewable any time from that spectrum's Metadata view, or from
        Operations History &rarr; Parameters &rarr; Per-Spectrum Detail. This history is shared
        with other operations that record one (currently SVD Background and Manual Baseline),
        so applying more than one of them to the same spectrum shows all of them together, in
        the order they actually happened, rather than each operation keeping a separate,
        disconnected record.
    </div>

    <div class="tip">
        <strong>Recommended workflow:</strong> load spectra &rarr;
        cross-spectrum cosmic ray removal &rarr; then apply other
        processing steps (baseline, normalisation, etc.). Removing cosmic
        rays first prevents them from distorting the baseline correction.
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
