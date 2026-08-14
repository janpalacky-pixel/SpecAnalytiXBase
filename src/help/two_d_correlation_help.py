# src/help/two_d_correlation_help.py

def get_two_d_correlation_help_title():
    return '2D Correlation (2D-COS) — Help'

def get_two_d_correlation_help_content():
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

    <h1>2D Correlation Spectroscopy (2D-COS)</h1>

    <p>2D correlation analysis (Noda, 1993) takes a stacked set of 1D
    spectra &mdash; each recorded under a different value of some external
    <strong>perturbation</strong> (time, temperature, concentration, pH,
    pressure, applied stress, &hellip;) &mdash; and transforms them into two
    square maps, each plotting one wavenumber against another:</p>
    <ul>
        <li><strong>Synchronous spectrum &Phi;(&nu;<sub>1</sub>,&nu;<sub>2</sub>)</strong>
            &mdash; bands that change <em>in phase</em> (simultaneously) as
            the perturbation varies.</li>
        <li><strong>Asynchronous spectrum &Psi;(&nu;<sub>1</sub>,&nu;<sub>2</sub>)</strong>
            &mdash; bands that change <em>out of phase</em> (one lags or
            leads the other) as the perturbation varies.</li>
    </ul>
    <p>The power of the method is resolving overlapping bands: two bands
    that look like one broad peak in the original 1D spectra can show up
    as two distinct, separable peaks here, because they respond
    differently to the perturbation even if they sit at nearly the same
    wavenumber.</p>

    <div class="note">
        <strong>How it's computed:</strong> each spectrum has a
        <em>reference</em> subtracted (the average of all spectra, by
        default) to give the "dynamic spectra" Y. The synchronous
        spectrum is &Phi; = Y<sup>T</sup>Y / (m&minus;1); the asynchronous
        spectrum applies the Hilbert&ndash;Noda transform along the
        spectrum order first: &Psi; = Y<sup>T</sup>NY / (m&minus;1), where
        N is the standard Noda transformation matrix. This assumes the
        spectra are evenly spaced along the perturbation variable &mdash;
        the standard assumption for this method, and the reason spectra
        should be selected/ordered by their real perturbation sequence
        (e.g. by time or temperature), not arbitrarily.
    </div>

    <hr>
    <h2>Settings</h2>
    <table>
        <tr><th>Setting</th><th>Description</th></tr>
        <tr><td><strong>Reference spectrum</strong></td>
            <td><span class="fm">Average of all spectra</span> (recommended
                default): the dynamic spectra are each spectrum minus the
                mean spectrum. <span class="fm">First spectrum</span> or
                <span class="fm">Specific spectrum&hellip;</span>: use instead
                when one particular spectrum in the selection genuinely
                represents a starting/blank state (e.g. before a reaction
                begins) rather than just being an arbitrary member of the
                series. "Specific spectrum&hellip;" reveals a second dropdown
                to pick any spectrum from the current selection, not just the
                first.</td></tr>
        <tr><td><strong>Perturbation values&hellip;</strong></td>
            <td>Optional. Enter the real value (temperature, time, &hellip;)
                for each spectrum, or load them from a text file (one number
                per line, same order as the spectra) — select cells and use
                Ctrl+C / Ctrl+X / Ctrl+V / Delete to fill values in from a
                spreadsheet, the same as the Rename Spectra table. If given,
                spectra are sorted into increasing perturbation order, and if
                the values turn out to be <em>unevenly</em> spaced, the
                dynamic spectra are automatically resampled onto a synthetic,
                evenly-spaced grid before computing either map — the
                asynchronous transform requires even spacing to be valid
                (see Practical tips). If left unset, spectra are assumed to
                already be in evenly-spaced order as selected. A status note
                appears after Run if resampling happened; click
                <strong>Resampling details&hellip;</strong> (appears once
                perturbation values have been used) to see exactly which
                original value and which synthetic grid value was used for
                every spectrum.</td></tr>
    </table>

    <hr>
    <h2>Hetero 2D Correlation</h2>
    <p>Standard ("homo") 2D-COS correlates a dataset against itself.
    <strong>Hetero 2D correlation</strong> is a genuine extension of the same
    method (also due to Noda) that instead correlates the dynamic spectra of
    <em>two different datasets</em> directly against each other — e.g. IR
    band positions against Raman band positions measured at the same time
    points — producing one combined map rather than two separate ones to
    compare by eye.</p>
    <ul>
        <li>Select <strong>all</strong> spectra for <em>both</em> datasets in
            the main window before opening this dialog (e.g. your IR spectra
            and your Raman spectra together), then tick
            <strong>Enable hetero mode</strong> and assign them: select the
            Dataset X spectra in the left list and the Dataset Y spectra in
            the right list (each list is selected independently — the two
            selections can even overlap, though that's rarely useful).</li>
        <li>Dataset X and Dataset Y do <strong>not</strong> need to share a
            wavenumber axis — that's the point of hetero correlation — but
            each dataset's own spectra must share one axis internally, and X
            and Y must have the <strong>same number</strong> of spectra, with
            the i-th selected X spectrum paired with the i-th selected Y
            spectrum (same perturbation step, e.g. same time point).</li>
        <li>Reference spectrum is Average or First, chosen independently for
            X and Y. Perturbation values and automatic resampling aren't
            supported in hetero mode — both datasets are assumed already
            evenly spaced and correctly ordered.</li>
        <li>Results appear in the <strong>Hetero Synchronous</strong> and
            <strong>Hetero Asynchronous</strong> tabs. The matrix is
            generally not square (Dataset X and Y can have different numbers
            of points), so there's no diagonal line — every point is
            genuinely a cross-relationship between an X band and a Y band,
            there's no such thing as an "autopeak" here.</li>
    </ul>

    <hr>
    <h2>Synchronous tab</h2>
    <p>Contour map of &Phi;(&nu;<sub>1</sub>,&nu;<sub>2</sub>), symmetric
    about the diagonal (dashed line). Two features to read:</p>
    <ul>
        <li><strong>Autopeaks</strong> &mdash; on the diagonal itself.
            Always positive. Their intensity reflects how much that band's
            intensity changes overall across the series; a large autopeak
            marks a band that responds strongly to the perturbation.</li>
        <li><strong>Cross peaks</strong> &mdash; off the diagonal, at
            (&nu;<sub>1</sub>,&nu;<sub>2</sub>) for two different bands.
            <strong>Positive</strong> (red, by default) means the two bands
            change in the <em>same</em> direction together (both increase,
            or both decrease). <strong>Negative</strong> (blue) means they
            change in <em>opposite</em> directions (one increases while the
            other decreases).</li>
    </ul>

    <hr>
    <h2>Asynchronous tab</h2>
    <p>Contour map of &Psi;(&nu;<sub>1</sub>,&nu;<sub>2</sub>),
    <strong>antisymmetric</strong> about the diagonal (&Psi;(&nu;<sub>1</sub>,&nu;<sub>2</sub>)
    = &minus;&Psi;(&nu;<sub>2</sub>,&nu;<sub>1</sub>) &mdash; the diagonal
    itself is always exactly zero). A cross peak here means the two bands
    change at <em>different rates or in a different sequence</em> as the
    perturbation progresses, even if a corresponding synchronous cross peak
    also exists.</p>

    <div class="tip">
        <strong>Noda's rules, in short:</strong> for a cross peak at the
        same (&nu;<sub>1</sub>,&nu;<sub>2</sub>) in both maps, if the
        synchronous and asynchronous cross peaks have the <strong>same
        sign</strong> (both positive or both negative), the band at
        &nu;<sub>1</sub> changes <em>before</em> the band at
        &nu;<sub>2</sub> as the perturbation increases. If they have
        <strong>opposite signs</strong>, &nu;<sub>1</sub> changes
        <em>after</em> &nu;<sub>2</sub>. (Reverse this rule if the
        synchronous autopeak at &nu;<sub>1</sub> is negative, which
        shouldn't normally happen, or if the perturbation variable is
        decreasing rather than increasing across the series.) A near-zero
        asynchronous cross peak means the two bands are changing
        essentially simultaneously &mdash; there's no sequence information
        to extract, only the synchronous relationship.
    </div>

    <hr>
    <h2>Dynamic spectra tab</h2>
    <p>The actual mean/first-subtracted spectra that both maps above are
    computed from — a sanity check before interpreting the maps. If this
    looks like noise rather than clean, systematic band changes, the maps
    will too; that usually means the spectra need better baseline
    correction or normalisation first, or that the selected spectra don't
    actually vary systematically with a real perturbation.</p>

    <hr>
    <h2>Display options</h2>
    <ul>
        <li><strong>Equal aspect</strong> — forces both wavenumber axes to
            the same visual scale, so the diagonal is a true 45&deg; line.
            Off by default: turning it on and then zooming to a region
            that isn't itself square (almost any rectangle-zoom) will shrink
            the plot to a sliver — a matplotlib limitation, not a bug. Turn
            it on to admire the symmetric full view; turn it back off before
            zooming into a specific region.</li>
        <li><strong>Noise threshold</strong> — hides correlation values
            smaller than this percentage of the map's own peak magnitude
            (rendered as white, matching the colormap's zero point).
            Particularly useful on the asynchronous map, which is often
            dominated by fine noise that obscures genuine cross peaks.</li>
        <li><strong>Link zoom</strong> — zooming or panning either the
            Synchronous or Asynchronous map applies the same view to the
            other, since reading a cross peak means checking its sign in
            both maps at the same (&nu;<sub>1</sub>,&nu;<sub>2</sub>)
            location.</li>
    </ul>

    <hr>
    <h2>Click-to-inspect</h2>
    <p>Click anywhere on the Synchronous or Asynchronous map to read the
    exact &Phi; and &Psi; values at that point in the status line below the
    tabs, along with an automatic Noda's-rule reading (see Asynchronous tab
    above) when the point is a genuine cross peak — reading exact signs off
    a small colour swatch is easy to get wrong; this gives the real numbers
    instead. (Note: while the toolbar's zoom or pan tool is active, a
    click-drag to zoom will also trigger a reading for wherever the drag
    started — harmless, just switch back to the default pointer tool for
    precise readings.)</p>

    <hr>
    <h2>Difference (A &minus; B) tab / Compare runs</h2>
    <p><strong>Store as A</strong> and <strong>Store as B</strong> each save a
    full snapshot of the <em>current</em> result — both the Synchronous and
    Asynchronous maps together, not one map per button. Use the dropdown to
    choose which of the two you want the difference for. <strong>Save
    A&hellip;</strong>/<strong>Save B&hellip;</strong> stay greyed out until
    that slot actually holds something (from Store or Load) — there's
    nothing to write to a file otherwise.</p>
    <p>To see anything other than a blank, all-zero plot: click
    <strong>Store as A</strong>, change something that actually affects the
    computation (the reference spectrum, or the perturbation values), click
    <strong>Run 2D Correlation</strong> again, then click <strong>Store as
    B</strong>. If A and B hold the same result, A &minus; B is exactly zero
    everywhere — that's the correct, expected outcome, not a bug (the dialog
    will warn you if this happens).</p>
    <p><strong>Save A&hellip; / Save B&hellip; / Load A&hellip; / Load
    B&hellip;</strong> write or read a stored snapshot as a <span class="fm">.npz</span>
    file, so A and B can come from <em>entirely separate dialog sessions</em>
    — not just different settings within one session. This is how to compare
    two genuinely different selections (e.g. heating-phase spectra vs.
    cooling-phase spectra of the same DNA melting experiment): select only
    the heating spectra, run, click Save A&hellip; to a file; close the
    dialog, reopen it with only the cooling spectra selected, run, click
    Save B&hellip; to a different file; then, in either session, use Load
    A&hellip; / Load B&hellip; to bring both saved snapshots together into
    one Difference tab. A and B must share the same wavenumber axis to be
    compared (true for two phases of the same experiment measured on the
    same instrument).</p>

    <hr>
    <h2>Practical tips</h2>
    <ul>
        <li><strong>Order and spacing matter.</strong> Select and order
            spectra by their real perturbation sequence (time, temperature,
            &hellip;) &mdash; the asynchronous transform requires evenly
            spaced samples. If your real steps aren't evenly spaced, use
            <strong>Perturbation values&hellip;</strong> to enter the actual
            numbers: spectra will be sorted correctly and, if the spacing
            is uneven, automatically resampled onto a synthetic even grid
            before computing either map. Without perturbation values, the
            spectra are assumed to already be evenly spaced in the order
            given — an arbitrary or shuffled selection order (with no
            perturbation values to correct it) will produce a meaningless
            asynchronous map (the synchronous map is order-independent and
            unaffected either way).</li>
        <li><strong>Pre-process first.</strong> Apply baseline correction
            and normalisation before 2D correlation, the same as for
            PCA/SVD/NMF — an uncorrected baseline drift is itself a slow
            "perturbation" that will dominate both maps with a spurious
            broad correlation.</li>
        <li><strong>At least 3 spectra are required</strong> — the
            asynchronous transform needs enough points along the
            perturbation axis for the Hilbert&ndash;Noda transform to mean
            anything; in practice, meaningful asynchronous maps typically
            need considerably more than the minimum.</li>
        <li>Compare against PCA/SVD loadings or NMF components for the same
            selection &mdash; bands that show strong 2D-COS cross peaks
            often correspond to components that co-vary in those
            decompositions too.</li>
    </ul>

    <hr>
    <h2>Saving data</h2>
    <p>The <strong>Save…</strong> button opens a dialog with the same shape
    as PCA/SVD/NMF's Save&hellip;:</p>
    <ul>
        <li><strong>File Format:</strong> Excel (.xlsx) or Text/CSV.</li>
        <li><strong>Include:</strong> Synchronous, Asynchronous, and/or
            Dynamic spectra &mdash; tick any combination; all three are
            included by default. Each matrix is saved as a full
            wavenumber &times; wavenumber grid, with the wavenumber values
            as both the row and column headers.</li>
        <li>For Text/CSV, choose a delimiter and decimal precision, and
            whether to combine everything into one file or write a
            separate file per category.</li>
    </ul>

    <div class="warn">
        <strong>Not a substitute for visual inspection.</strong> 2D
        correlation highlights <em>where</em> bands correlate, not
        <em>why</em> &mdash; always check candidate cross peaks against the
        original spectra (and the Dynamic spectra tab) before drawing
        conclusions, especially for asynchronous cross peaks near the
        noise level.
    </div>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    the spectrum list and axis tick labels on the 2D maps.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    <hr>
    <h2 id="references">References</h2>
    <p style="font-size: 12px;">
    Noda, I. (1993). Generalized Two-Dimensional Correlation Method
    Applicable to Infrared, Raman, and Other Types of Spectroscopy.
    <em>Applied Spectroscopy</em>, 47(9), 1329&ndash;1336. (Original
    generalized 2D-COS method and the synchronous/asynchronous maps
    computed here.)
    <br><br>
    Noda, I., &amp; Ozaki, Y. (2004). <em>Two-Dimensional Correlation
    Spectroscopy: Applications in Vibrational and Optical
    Spectroscopy</em>. John Wiley &amp; Sons, Chichester. (Full treatment,
    including the Hilbert&ndash;Noda transform and the interpretation
    rules for cross-peak signs summarized above.)
    </p>

    </body></html>
    """
