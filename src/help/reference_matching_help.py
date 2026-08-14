# src/help/reference_matching_help.py

def get_reference_matching_help_title():
    return 'Reference Library Matching — Help'

def get_reference_matching_help_content():
    return """
    <html><head><style>
        body  { font-family:Arial,sans-serif; margin:20px; line-height:1.6; font-size:13px; }
        h1    { color:#2E7D32; border-bottom:2px solid #2E7D32; }
        h2    { color:#1565C0; margin-top:22px; }
        h3    { color:#E65100; margin-top:14px; margin-bottom:4px; }
        .tip  { background:#E8F5E9; border-left:4px solid #2E7D32; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .note { background:#E3F2FD; border-left:4px solid #1565C0; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .warn { background:#FFF8E1; border-left:4px solid #F9A825; padding:10px 14px; border-radius:3px; margin:8px 0; }
        .fm   { font-family:monospace; background:#ececec; padding:1px 5px; border-radius:3px; }
        table { border-collapse:collapse; width:100%; margin:8px 0; }
        th    { background:#E3F2FD; text-align:left; padding:6px 8px; }
        td    { border-bottom:1px solid #e0e0e0; padding:5px 8px; vertical-align:top; }
        ul,ol { padding-left:20px; } li { margin:3px 0; }
        hr    { border:none; border-top:1px solid #ddd; margin:20px 0; }
    </style></head><body>

    <h1>Reference Library Matching</h1>

    <p>Compares each selected (query) spectrum against a library of reference
    spectra and ranks the references by similarity. Results are shown in a
    sortable table and an overlay preview plot.</p>

    <div class="note">
        <strong>Non-destructive:</strong> this operation never modifies
        spectrum data. Results are stored for the session and can be
        exported to CSV.
    </div>

    <hr>
    <h2>Workflow</h2>
    <p>There are two ways to define the reference library:</p>
    <ul>
        <li><strong>From loaded spectra</strong> (recommended) &mdash;
            select which of the currently loaded spectra act as references
            directly in the dialog. Query and reference spectra were
            processed with the same pipeline, so the comparison is
            meaningful. This mirrors the X-axis alignment workflow where
            one spectrum is the reference within the group.</li>
        <li><strong>From file(s)</strong> &mdash; load an external
            reference library from CSV/TXT/DAT/XLSX files.</li>
    </ul>
    <div class="warn">
        <strong>Pre-process query and reference spectra the same way.</strong>
        Similarity scores are only meaningful when both have been treated
        identically: same baseline correction, same spectral range, same
        normalisation. A fluorescence background that dominates the signal
        will produce high scores for spectrally unrelated samples.
        Recommended pipeline before matching: Data range &rarr; Baseline
        correction (SNIP or manual) &rarr; Reference matching.
    </div>

    <div class="note">
        <strong>A spectrum is never matched against itself.</strong> In
        <strong>From loaded spectra</strong> mode, if the same spectrum is
        selected as both a query and a reference, that particular
        reference is skipped for that query &mdash; a spectrum trivially
        "matches" itself with a perfect score, which isn't a meaningful
        comparison. If a query's ONLY selected reference is itself, that
        query gets zero matches (the Preview and Results tabs both explain
        this directly when it happens) &mdash; select at least one
        different reference spectrum to get a real comparison.
    </div>

    <ol>
        <li>Choose <strong>From loaded spectra</strong> or
            <strong>From file(s)</strong> in the Reference library panel.
            Select which spectra act as references using the list
            (Ctrl+click, Shift+click, Select all / Clear).</li>
        <li>If using files: click <strong>Load library file(s)&hellip;</strong>
            then select which loaded references to use.</li>
        <li>Choose a <strong>metric</strong> and optional
            <strong>pre-normalisation</strong>.</li>
        <li>Select the query spectra in the list.</li>
        <li>In the <strong>Query spectra</strong> list, select which spectra
            to include in Results and Plots. Selection works like Excel:
            click selects one item, Shift+click extends the selection,
            Ctrl+click toggles individual items. Use
            <strong>Select all</strong> / <strong>Clear</strong> for bulk
            selection.</li>
        <li>Watch the <strong>Preview</strong> tab as you select query
            spectra — see below for how it adapts to how many are
            selected at once.</li>
        <li>Switch to the <strong>Results</strong> tab for the full
            ranked table. Export with Copy or Export CSV.</li>
    </ol>

    <hr>
    <h2>Preview: one spectrum, or several at once</h2>
    <p>What the <strong>Preview</strong> tab shows depends on how many query
    spectra are currently selected (blue-highlighted) in the Query spectra
    list:</p>
    <ul>
        <li><strong>One selected:</strong> a single plot — the black line is
            that query spectrum, coloured dashed lines are its top matches,
            each labelled with its rank and score.</li>
        <li><strong>Several selected:</strong> one subplot per selected
            query spectrum, stacked vertically, each showing that query and
            its own top matches — so you can compare several queries'
            matches side by side instead of checking them one at a time.
            This is capped by <strong>Max subplots</strong> (in the Query
            spectra panel, default 4) so the plot area doesn't get
            overcrowded with a large selection; if more spectra are
            selected than the cap allows, a note above the plot says
            &ldquo;Showing N of M selected query spectra&rdquo; rather than
            silently leaving the rest out. Raise the limit to see more at
            once, or lower it if the subplots feel too cramped to read. This
            setting only affects what the Preview tab draws — the
            <strong>Results</strong> table and CSV/Excel export always
            include every selected query spectrum regardless of it.</li>
        <li><strong>None selected:</strong> the Preview tab shows a
            placeholder message instead of leaving the last-viewed plot on
            screen (which could otherwise be a spectrum no longer part of
            the current selection at all).</li>
    </ul>
    <div class="note">
        <strong>Not to be confused with the Plots tab's own Max subplots.</strong>
        The Plots tab (bar charts of match scores) has its own, separate
        Max subplots setting — the two are independent and can be set to
        different values.
    </div>

    <hr>
    <h2>Library file format</h2>
    <p>The same format as spectral data files used for import:</p>
    <ul>
        <li>First column: x-axis (wavenumber / wavelength)</li>
        <li>Subsequent columns: one reference spectrum per column</li>
        <li>Optional header row with reference names</li>
        <li>Multiple files are merged — each column in each file becomes
            one library entry</li>
    </ul>
    <p>All auto-detection (delimiter, decimal separator, header) used by the
    main importer applies here as well.</p>

    <hr>
    <h2>X-axis overlap detection</h2>

    <p>Before computing any similarity score, the manager checks how much
    of the x-axis is shared between the query and reference spectrum:</p>
    <p style='margin-left:16px'>
        <span class='fm'>overlap % = min(overlap/query range,
        overlap/reference range) &times; 100</span>
    </p>
    <p>Matches where the overlap is below the <strong>Min overlap %</strong>
    threshold (default 50&nbsp;%) are flagged as unreliable:</p>
    <ul>
        <li>Score shown as &mdash; (not computed)</li>
        <li>Overlap % shown in red in the Results table</li>
        <li>Row text greyed out</li>
        <li>Unreliable matches are always ranked below reliable ones</li>
    </ul>
    <div class='warn'>
        <strong>This protects against the most common pitfall:</strong>
        comparing spectra measured on completely different x-scales
        (e.g. Raman 400&ndash;3000&nbsp;cm&sup1; vs CD 200&ndash;400&nbsp;nm)
        produces extrapolated flat lines and misleadingly high
        similarity scores. Overlap detection prevents this.
    </div>

    <hr>
    <h2>Similarity metrics</h2>

    <table>
        <tr><th>Metric</th><th>Formula</th><th>Properties</th></tr>
        <tr>
            <td><strong>cosine</strong> (default)</td>
            <td><span class="fm">dot(a,b) / (||a|| &times; ||b||)</span></td>
            <td>Scale-invariant. 1 = perfect match, &minus;1 = perfect
                anti-correlation, 0 = orthogonal. Best for comparing
                spectral shapes regardless of intensity.</td>
        </tr>
        <tr>
            <td><strong>pearson</strong></td>
            <td>Pearson correlation coefficient</td>
            <td>Linear correlation, mean-centred.
                1 = perfect positive correlation.
                Sensitive to baseline offset.</td>
        </tr>
        <tr>
            <td><strong>euclidean</strong></td>
            <td><span class="fm">1 / (1 + ||a &minus; b||)</span></td>
            <td>Distance-based, bounded to (0,&nbsp;1].
                Sensitive to both shape and intensity scale.
                Pre-normalisation strongly recommended.</td>
        </tr>
    </table>

    <hr>
    <h2>Which metric to choose?</h2>
    <p>In practice for Raman and IR spectra:</p>
    <ul>
        <li><strong>Cosine</strong> is the most commonly used. It measures
            the angle between two spectral vectors — identical spectra give
            1.0, completely orthogonal spectra give 0.0. It is inherently
            scale-invariant, so pre-normalisation has no effect on cosine
            scores (vector-normalising then computing cosine is
            mathematically identical to cosine without normalisation).
            <strong>Caveat: raw, non-baseline-corrected spectra that share a
            large positive offset (e.g. an unremoved Raman/fluorescence
            background) can score close to 1.0 even when their PEAK
            SHAPES look quite different</strong> — a large shared baseline
            dominates the dot product, and cosine has no notion of
            "constant offset" to subtract out first. If two spectra you
            expect to look different are scoring suspiciously high (say,
            &gt;0.98) despite visibly different shapes on the Preview
            plot, this is almost always why — baseline-correct both
            first, or try Pearson (below), which is unaffected by a
            constant offset.</li>
        <li><strong>Pearson</strong> gives similar values to cosine for
            most spectra. The difference: Pearson mean-centres each spectrum
            first, making it insensitive to a constant baseline offset.
            For spectra with a flat fluorescence background, or the
            baseline-offset situation described above, Pearson will
            discriminate genuinely different shapes much better than
            cosine.</li>
        <li><strong>Euclidean</strong> <span class="fm">1/(1+||a&minus;b||)</span>
            measures absolute distance. It is sensitive to both shape and
            intensity scale. After vector normalisation, spectra lie on the
            unit sphere and the Euclidean distance equals the chord length
            — a stricter criterion than the angle. Scores are close to 1.0
            only for nearly identical spectra. Use this when you need
            high discrimination and have already normalised your spectra.</li>
    </ul>
    <div class="note">
        <strong>Pre-normalise and cosine:</strong> applying vector
        normalisation before cosine scoring has no effect on the score
        (cosine is already scale-invariant). Pre-normalisation is most
        useful with the euclidean metric.
    </div>

    <hr>
    <h2>Pre-normalisation</h2>

    <table>
        <tr><th>Method</th><th>Description</th></tr>
        <tr><td><strong>none</strong></td>
            <td>Use spectra as-is. Only appropriate if query and
                references are already on the same intensity scale.</td></tr>
        <tr><td><strong>vector</strong></td>
            <td>Divide by L2 norm. Makes cosine similarity independent
                of total intensity. Recommended default with cosine.</td></tr>
        <tr><td><strong>max_peak</strong></td>
            <td>Scale so the maximum intensity = 1. Intuitive for
                comparing band patterns.</td></tr>
        <tr><td><strong>unit_area</strong></td>
            <td>Scale so the total spectral area = 1. Useful when
                comparing concentration-normalised spectra.</td></tr>
    </table>

    <div class="tip">
        <strong>Recommended combination:</strong> cosine similarity +
        vector normalisation. This gives a score of 1 for identical
        spectra and is robust to intensity differences between query
        and library.
    </div>

    <hr>
    <h2>Plots tab</h2>
    <p>The Plots tab shows one bar chart per query spectrum (up to Max subplots).
    All subplots share the same x-axis (the union of all reference labels across
    shown queries), making it easy to compare which references score high across
    multiple query spectra.</p>
    <ul>
        <li><strong>Coloured bars</strong> — references that appear in this
            query's top-N matches, ranked by colour. The default palette cycles
            through 5 colours: orange (rank 1), blue (rank 2), green (rank 3),
            purple (rank 4), teal (rank 5), then repeats. Choose a different
            <strong>Bar colours</strong> palette (e.g. coolwarm, viridis, RdYlGn)
            to map rank to a continuous colourmap instead.</li>
        <li><strong>Light grey bars</strong> — references present in another
            query's top-N but not this query's. Their bar is drawn at the Y min
            level so the shared x-axis remains consistent. This is intentional —
            a grey bar means "this reference was not among the top matches for
            this query".</li>
        <li><strong>Y min</strong> — set the minimum y-axis value (default 0.9)
            to zoom in on score differences near 1.0.</li>
        <li><strong>Max subplots</strong> — limit the number of query spectra
            shown (default 5). Increase for larger comparisons.</li>
    </ul>

    <hr>
    <h2>Interpreting results</h2>

    <p>The Results table shows one row per (query spectrum, match) pair.
    Rank 1 is always the best match. The Score column uses the selected
    metric — higher is always better for all three metrics.</p>

    <div class="warn">
        <strong>Negative cosine scores</strong> (shown in red in the Results
        table) indicate anti-correlation &mdash; the query and reference have
        opposite spectral shapes. This is common with CD (circular dichroism)
        spectra that contain both positive and negative bands. A negative score
        does not mean "no match" &mdash; it means the spectra are mirror-image
        in sign. Consider using <strong>Pearson correlation</strong> or
        applying baseline correction before matching CD spectra.
    </div>
    <div class="warn">
        <strong>Score thresholds are metric-dependent.</strong>
        A cosine score &gt; 0.99 is a very strong match; &gt; 0.95 is
        typically a good match for Raman spectra. Euclidean scores depend
        heavily on normalisation. Do not compare scores across different
        metric settings.
    </div>

    <div class="tip">
        <strong>Preprocessing tip:</strong> for best results, apply the
        same preprocessing pipeline (baseline correction, normalisation)
        to both the query spectra and the reference library before
        matching. Raw spectra with fluorescence backgrounds will give
        misleading similarity scores.
    </div>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    the query/reference spectrum lists, the Results table, and the plots' legends/titles.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body></html>
    """
