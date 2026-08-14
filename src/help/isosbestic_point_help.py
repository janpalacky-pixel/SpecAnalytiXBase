# src/help/isosbestic_point_help.py


def get_isosbestic_point_help_title():
    return 'Isosbestic / Isodichroic Point Detection — help'


def get_isosbestic_point_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            h4    { color: #4A148C; margin-top: 12px; margin-bottom: 2px; }
            .cat    { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .detail { background: #FAFAFA; border-left: 4px solid #E65100;
                      padding: 10px 14px; margin: 6px 0 14px 0; border-radius: 3px; }
            .tip    { background: #E8F5E9; border-left: 4px solid #2E7D32;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note   { background: #E3F2FD; border-left: 4px solid #1565C0;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn   { background: #FFF8E1; border-left: 4px solid #F9A825;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm     { font-family: monospace; background: #ececec;
                      padding: 1px 5px; border-radius: 3px; }
            .back-link { font-size: 11px; color: #888; }
            .det-link  { font-size: 11px; color: #1565C0; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        </style>
    </head>
    <body>
    <a name="top"></a>

    <h1>Isosbestic / Isodichroic Point Detection</h1>

    <p>Finds the x-axis location(s) where a SERIES of spectra &mdash;
    recorded along some interconversion coordinate such as a titration,
    a temperature ramp, a pH series, or a time course &mdash; all cross
    through the same y-value. This kind of read-only analysis works
    directly on the spectra you select: it never adds, removes, or
    modifies any spectrum, so there's no Apply/Add as New step and
    nothing is written to Operations History &mdash; the Results table
    and its Copy/Export CSV buttons are the whole output.</p>

    <hr>
    <h2 id="concept">What is an isosbestic/isodichroic point?</h2>

    <p>When a sample interconverts cleanly between exactly TWO species
    (A and B) &mdash; and nothing else &mdash; the observed spectrum at
    any point along that interconversion is a simple mixture:</p>
    <div class="cat">
        <p><span class="fm">y_observed(x) = f &middot; y_A(x) + (1&minus;f) &middot; y_B(x)</span></p>
    </div>
    <p>where <span class="fm">f</span> is the fraction of species A
    present (0 to 1, changing as the titration/temperature/time
    progresses). At any x where the two species happen to have the SAME
    signal (<span class="fm">y_A(x) = y_B(x)</span>), the mixture
    formula above reduces to that same value regardless of
    <span class="fm">f</span> &mdash; so EVERY spectrum in the series,
    no matter how far along the interconversion, passes through exactly
    that point. That's the isosbestic point (absorption/UV-Vis
    terminology) or isodichroic point (the same concept, used in CD
    spectroscopy). Its presence is often taken as evidence that the
    system really does involve just two species with no significant
    side reactions or intermediates &mdash; a third species would
    generally not share that same crossing value, and the clean common
    crossing would degrade or disappear.</p>

    <hr>
    <h2 id="how-it-works">How detection works</h2>

    <p>All selected spectra must already share one identical x-axis (use
    the <strong>Data Range</strong> operation with linearisation first
    if they don't &mdash; the same requirement as SVD, PCA, Cluster
    Analysis, MCR-ALS, and NMF, which also stack spectra into one
    matrix). With that in hand:</p>
    <ol>
        <li>At every x-value, compute the <strong>standard deviation</strong>
            of the y-values across all selected spectra &mdash; how much
            they disagree with each other, at that one point.
            <a class="det-link" href="#det-curve">&#9660; algorithm details</a></li>
        <li>A genuine isosbestic/isodichroic point is a <strong>local
            minimum</strong> of that disagreement curve &mdash; a
            wavelength where the spectra collapse tightly together,
            bracketed on both sides by wavelengths where they visibly
            fan out.</li>
        <li>Not every dip is real: noise alone can produce small,
            shallow wiggles anywhere in the curve. This operation uses
            each candidate's <strong>topographic prominence</strong>
            (see the Minimum Prominence '?' button in the dialog for the
            precise definition) to keep only dips that stand out clearly
            from the surrounding baseline disagreement, filtered by a
            sensitivity threshold you control.
            <a class="det-link" href="#det-curve">&#9660; algorithm details</a></li>
        <li>Neither is every dip <em>meaningful</em>, even a genuinely
            deep and prominent one: a flat, signal-free stretch of
            x-axis &mdash; a baseline gap between two well-separated
            bands, where NEITHER interconverting species has any real
            signal &mdash; also produces a near-zero disagreement, since
            every spectrum simply reads ~0 there together. That's not an
            isosbestic point; nothing is actually crossing. The
            <strong>Minimum Signal Level</strong> control (see its '?'
            button) filters these out by requiring genuine, non-trivial
            signal at the candidate location.
            <a class="det-link" href="#det-signal">&#9660; algorithm details</a></li>
        <li>Each kept candidate's x-location is refined slightly beyond
            the raw data-point spacing using a parabola fit through the
            minimum and its two neighbouring points &mdash; a standard
            sub-grid refinement, not a new measurement.
            <a class="det-link" href="#det-refine">&#9660; algorithm details</a></li>
    </ol>

    <hr>
    <h2 id="reading-results">Reading the results table</h2>
    <table>
        <tr><th>Column</th><th>Meaning</th></tr>
        <tr><td>X</td><td>The candidate isosbestic/isodichroic point's location.</td></tr>
        <tr><td>Mean Y</td><td>Average y-value of all selected spectra at that x — the
            signal level shared by every spectrum at the crossing.</td></tr>
        <tr><td>Std across spectra</td><td>How tightly the spectra actually agree
            there, in the spectra's own y-units — smaller is better.</td></tr>
        <tr><td>Prominence</td><td>How distinctive this dip is compared to the
            surrounding disagreement level — larger means a cleaner, more
            convincing crossing.</td></tr>
        <tr><td>Relative tightness</td><td>Std across spectra divided by the
            TYPICAL (median) disagreement across the whole searched range —
            a scale-independent number; close to 0 means the spectra agree
            far better here than they typically do elsewhere.
            <a class="det-link" href="#det-tightness">&#9660; algorithm details</a></td></tr>
    </table>

    <hr>
    <h2 id="caveats">Caveats</h2>
    <div class="warn">
    <ul>
        <li><strong>Needs at least 3 spectra to be meaningful.</strong> With
            only 2, any two non-parallel curves cross SOMEWHERE trivially —
            that alone proves nothing about a genuine two-species
            equilibrium. This operation will still run with 2 and shows a
            warning, but treat the result with real skepticism.</li>
        <li><strong>Only detects a point common to ALL selected spectra.</strong>
            Including an unrelated spectrum (a different sample, a
            different equilibrium, an artifact-laden outlier) in the
            selection can hide a real crossing or lower its prominence
            below the detection threshold. If you don't see the crossing
            you expect, try removing spectra you're not sure belong to the
            same series.</li>
        <li><strong>Presence of a common crossing point is evidence for,
            not proof of, a clean two-state process.</strong> More complex
            systems (three or more species, or two species whose molar
            signal ratio itself changes, e.g. with pH-dependent shifts)
            can sometimes still show an approximate common crossing by
            coincidence, or fail to show one even with a genuine two-state
            process if the spectra are noisy. Use this as one piece of
            supporting evidence alongside the rest of your analysis, not a
            standalone conclusion.</li>
        <li><strong>Resolution is limited by your data's x-axis spacing.</strong>
            The sub-grid parabola refinement improves on the raw grid
            spacing, but the result is still only as precise as the
            underlying measurement — do not over-interpret the last
            reported digit.</li>
    </ul>
    </div>

    <hr>
    <!-- TECHNICAL DETAILS -->
    <h2>Technical details</h2>

    <div class="detail">
        <a name="det-curve"></a>
        <h3>Disagreement curve, local minima, and prominence</h3>
        <p>With all N selected spectra stacked into one matrix (rows =
        spectra, columns = shared x-axis points), two curves are computed
        at every x-column:</p>
        <p>&nbsp;&nbsp;<span class="fm">std_curve(x) = std_i( y_i(x) )</span>
        &nbsp;&nbsp;(sample standard deviation across the N spectra, ddof=1)</p>
        <p>&nbsp;&nbsp;<span class="fm">mean_curve(x) = mean_i( y_i(x) )</span></p>
        <p><strong>Implementation:</strong>
        <span class="fm">scipy.signal.find_peaks(-std_curve, prominence=min_prominence)</span>
        &mdash; negating the curve turns every local minimum (valley) of
        <span class="fm">std_curve</span> into a local maximum (peak) that
        <span class="fm">find_peaks</span> can detect directly.</p>
        <p><strong>Prominence</strong> (scipy's topographic definition): from
        a candidate valley, walk outward in both directions until you reach
        either a point lower than the valley itself, or the edge of the
        search range &mdash; take the higher of the two paths' lowest point
        reached along the way, and prominence is the vertical drop from that
        reference level down to the valley. A shallow wiggle sitting on a
        noisy but otherwise flat curve has low prominence; a valley that
        genuinely stands apart from everything else in the range has high
        prominence.</p>
        <p><strong>Threshold used:</strong>
        <span class="fm">min_prominence = (min_prominence_pct / 100) &times; variation_range</span>,
        where <span class="fm">variation_range = max(std_curve) &minus; min(std_curve)</span>
        over the searched x-range &mdash; so the Minimum Prominence percentage
        is relative to how much the spectra disagree anywhere in that range,
        not an absolute y-unit.</p>
    </div>

    <div class="detail">
        <a name="det-signal"></a>
        <h3>Minimum signal level filter</h3>
        <p>A point is <strong>significant</strong> if:</p>
        <p>&nbsp;&nbsp;<span class="fm">|mean_curve(x)| &ge; (min_signal_pct / 100) &times; max( |mean_curve| )</span></p>
        <p>where the maximum is taken over the whole searched x-range. Only
        candidates at significant x-points are kept in the results.</p>
        <p><strong>Design note:</strong> this significance test is applied
        to the list of candidates that <span class="fm">find_peaks</span>
        already found on the untouched <span class="fm">std_curve</span>
        &mdash; insignificant ones are simply dropped afterward, rather than
        being edited into the curve before peak-finding runs. An earlier
        version of this filter instead overwrote insignificant points with
        an artificial sentinel value <em>before</em> calling
        <span class="fm">find_peaks</span>, to keep them from being detected
        as valleys at all. That approach introduced a hard artificial cliff
        at every mask boundary, and <span class="fm">find_peaks</span> would
        occasionally mistake the last still-significant point on the
        shoulder of a decaying peak (where std is small and still trending
        down) for a genuine valley bottom, since the very next point jumped
        straight to the sentinel. Filtering the results afterward, on the
        real unmodified curve, finds the same genuine local minima without
        that artifact.</p>
        <p>The <strong>typical disagreement</strong> used by the Relative
        tightness column (see below) is also computed only from significant
        points &mdash; <span class="fm">typical_std = median(std_curve)</span>
        restricted to that subset &mdash; so long flat, signal-free
        stretches (common in real spectra) don't drag the reference value
        down and make every genuine candidate look artificially loose by
        comparison.</p>
    </div>

    <div class="detail">
        <a name="det-refine"></a>
        <h3>Sub-grid parabola refinement</h3>
        <p>For a local minimum at grid index <span class="fm">i</span>
        (with neighbours <span class="fm">i&minus;1</span> and
        <span class="fm">i+1</span>), a parabola is fit through the three
        <span class="fm">std_curve</span> values
        <span class="fm">y_L, y_M, y_R</span> in fractional-index space, and
        its vertex gives a sub-grid offset:</p>
        <p>&nbsp;&nbsp;<span class="fm">&delta; = 0.5 &times; (y_L &minus; y_R) / (y_L &minus; 2y_M + y_R)</span>,
        &nbsp;clamped to [&minus;0.5, +0.5]</p>
        <p>This offset is then mapped back to x by linear interpolation
        toward whichever neighbouring grid point it points at &mdash; robust
        to non-uniform x-spacing, since it never assumes a fixed step size.
        At the edges of the searched range (no neighbour on one side), or if
        the three points are exactly collinear (denominator would be zero),
        the plain grid point is returned unrefined.</p>
    </div>

    <div class="detail">
        <a name="det-tightness"></a>
        <h3>Relative tightness</h3>
        <p>&nbsp;&nbsp;<span class="fm">relative_tightness = std_curve(x_candidate) / typical_std</span></p>
        <p>where <span class="fm">typical_std</span> is the median of
        <span class="fm">std_curve</span> over the significant region only
        (see above). This is a scale-independent way to judge a candidate
        against its own dataset: a value near 0 means the spectra agree far
        more tightly there than they typically do across the searched
        range &mdash; the strongest signature of a genuine crossing.
        A value close to 1 means the local minimum isn't really any
        tighter than a typical point in the range, which is often the
        case for a shallow, borderline local dip that only barely cleared
        the prominence threshold.</p>
    </div>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
