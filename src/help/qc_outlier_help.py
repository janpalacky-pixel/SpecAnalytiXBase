# src/help/qc_outlier_help.py


def get_qc_outlier_help_title():
    return 'QC / Outlier Detection — help'


def get_qc_outlier_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
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
            .det-link  { font-size: 11px; color: #1565C0; }
            .back-link { font-size: 11px; color: #888; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
            hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
            pre   { background:#282c34; color:#abb2bf; padding:10px 14px; border-radius:4px; overflow-x:auto; }
        </style>
    </head>
    <body>
    <a name="top"></a>

    <h1>QC / Outlier Detection</h1>

    <p>Checks a batch of spectra against EACH OTHER and flags any that
    don't look like they belong &mdash; a bad acquisition, a
    contaminated or mislabeled sample, an instrument glitch, anything
    that stands out from the rest of the group. This is a read-only
    analysis tool: it never adds, removes, or transforms spectral data,
    so there's no Apply/Add as New step and nothing is written to
    Operations History &mdash; it only tells you what to go look at.</p>

    <div class="tip">New to this tool? Jump straight to
    <a href="#tutorial">Try it yourself &mdash; bundled demo dataset</a>
    for a guided walkthrough with a known right answer.</div>

    <hr>
    <h2 id="concept">The idea</h2>
    <p>A PCA model is fitted to the whole selected batch (see
    <a href="#technical">Technical details</a> for the exact model), then
    every spectrum is scored on two independent, complementary
    diagnostics:</p>
    <ul>
        <li><strong>Hotelling T&sup2;</strong> &mdash; how far a
            spectrum sits from the bulk of the batch, WITHIN the model.
            High T&sup2; means an unusual but still model-shaped
            spectrum &mdash; e.g. an atypically strong or weak version
            of the variation the rest of the batch already shows (an
            unusually concentrated sample, a real but extreme
            member).</li>
        <li><strong>Q-residual (SPE)</strong> &mdash; how much of a
            spectrum's shape the model does NOT explain at all. High Q
            means the spectrum doesn't look like the rest of the batch's
            spectral family in the first place &mdash; e.g. a spike, a
            baseline artifact, contamination, an instrument glitch, a
            genuinely different sample.</li>
    </ul>
    <p>A spectrum can be flagged on either, both, or neither &mdash; they
    answer different questions, so a high T&sup2; with a low Q ("unusual
    but plausible member of the batch") means something different from a
    high Q with a low T&sup2; ("doesn't fit the batch's spectral shape at
    all"). The <strong>Flag</strong> column and the distance plot show
    you which is which.</p>

    <hr>
    <h2 id="workflow">Workflow</h2>
    <ol>
        <li>Select the batch of spectra to check (at least 5 &mdash;
            there needs to be a real "batch" for anything to look
            unusual against), then open <strong>QC / Outlier
            Detection</strong>. All spectra must share one identical
            x-axis (use <strong>Data Range</strong> with linearisation
            first if they don't).</li>
        <li>Leave <strong>Auto-select components</strong> checked
            (recommended) or pick a number of components yourself.</li>
        <li>Leave the <strong>Confidence level</strong> at 95% unless you
            have a specific reason to be stricter (99%) or more lenient
            (90%) &mdash; see <a href="#settings">Settings</a>.</li>
        <li>Click <strong>Run QC Check</strong>.</li>
        <li>Read the <strong>results table</strong> (worst-first) and the
            <strong>View</strong> dropdown's plots &mdash; selecting a row
            in the table highlights that spectrum with a bold blue ring on
            the Distance plot / PCA scores view (wherever it's plotted),
            or switch View to <strong>Residual spectrum</strong> to see
            exactly what a flagged spectrum doesn't fit. Use the
            <strong>On row click</strong> dropdown (next to View) to
            change what selecting a row does to the plot: highlight the
            point only, replace the plot with that spectrum's full
            original curve, or show both side by side. <strong>Copy to
            clipboard</strong> or <strong>Export CSV</strong> to take the
            table elsewhere.</li>
    </ol>

    <hr>
    <h2 id="settings">Settings</h2>
    <table>
        <tr><th>Setting</th><th>Meaning</th></tr>
        <tr><td>Auto-select components</td><td>Picks the smallest number
            of PCA components whose cumulative explained variance
            reaches the threshold below (default 95%) &mdash; the
            standard "enough of the real signal, not just noise" rule of
            thumb. Uncheck to pick the component count yourself.</td></tr>
        <tr><td>Variance threshold</td><td>Only used when auto-select is
            on. Lower values keep the model simpler (and push more
            variation into the Q-residual, making Q more sensitive);
            higher values capture more of the batch's real variation
            into the model (and push more into T&sup2; instead).</td></tr>
        <tr><td>Number of components</td><td>Only used when auto-select
            is off. Capped so at least one component is always left over
            for the Q-residual to be computed from.</td></tr>
        <tr><td>Confidence level</td><td>How strict the control limits
            are (90/95/99%). 95% flags roughly 1 in 20 perfectly normal
            spectra by chance alone &mdash; a flag is a prompt to look
            closer, not automatic proof something is wrong. 99% is
            stricter (fewer false alarms, but also more likely to miss a
            real but subtle outlier).</td></tr>
    </table>

    <hr>
    <h2 id="reading-results">Reading the results</h2>

    <h3>View dropdown (plot)</h3>
    <table>
        <tr><th>View</th><th>Shows</th></tr>
        <tr><td>Distance plot (T&sup2; vs Q)</td><td>The classic
            "distance-distance" plot &mdash; every spectrum as one point,
            with the two control limits drawn as reference lines. Points
            in the upper-right, or past either line, are flagged (shown
            in red).</td></tr>
        <tr><td>PCA scores</td><td>The batch's first two PCA components
            (or PC1 vs. spectrum order, if only one component was
            retained) &mdash; a map of how the batch groups and spreads
            out, with flagged spectra marked.</td></tr>
        <tr><td>Residual spectrum (selected row)</td><td>For whichever
            spectrum is selected in the results table: its original
            spectrum, the model's reconstruction of it, and the
            difference between them &mdash; the most direct way to SEE
            why a flagged spectrum was flagged (a spike shows up as a
            sharp residual right where it is; a baseline offset shows up
            as a broad, flat residual).</td></tr>
    </table>

    <h3>Selecting a row in the results table</h3>
    <p>Whatever's currently plotted responds to the results table
    selection:</p>
    <ul>
        <li><strong>Distance plot / PCA scores</strong> (default): the
            selected spectrum's point gets a bold open blue ring around it
            and its label in bold blue &mdash; easy to find even among a
            crowded cluster of points, and visually distinct from both the
            plain blue "OK" dots and the red "Flagged" triangles.</li>
        <li><strong>Residual spectrum</strong>: selecting a row is what
            drives this view in the first place &mdash; it always shows
            whichever spectrum is currently selected.</li>
    </ul>

    <h3>"On row click" dropdown (next to View)</h3>
    <table>
        <tr><th>Option</th><th>What selecting a row does</th></tr>
        <tr><td>Highlight point (default)</td><td>Just highlights that
            point on the current View, as described above &mdash; nothing
            else changes.</td></tr>
        <tr><td>Full spectrum</td><td>REPLACES whatever View is showing
            with a single plain plot of that spectrum's own original
            curve &mdash; no model overlay, no residual panel, just "what
            does this spectrum actually look like." Quicker than
            switching View to Residual spectrum and back when all you
            want is a direct look, e.g. to see a spike or artifact with
            your own eyes.</td></tr>
        <tr><td>Both (split view)</td><td>Shows the current View plot
            (Distance plot / PCA scores / Residual spectrum) on the left
            and that spectrum's plain full original curve on the right,
            side by side &mdash; so you can see where a point sits AND
            what its spectrum looks like at the same time, without
            switching back and forth.</td></tr>
    </table>
    <p>Switch back to Highlight point at any time to return to the plain
    View-only display.</p>

    <h3>Results table</h3>
    <p>One row per spectrum, sorted <strong>worst-first</strong> (largest
    T&sup2;/limit or Q/limit ratio) so whatever's most worth looking at
    is always at the top. T&sup2; and Q values are shown in red when they
    exceed their control limit; the Flag column names which diagnostic
    (or both) triggered.</p>

    <hr>
    <h2 id="technical">Technical details</h2>

    <div class="detail">
        <h3>The model</h3>
        <p><strong>In plain terms:</strong> imagine laying every selected
        spectrum's intensity values out as one long row of numbers, and
        stacking all n spectra into a table (n rows, one column per x-axis
        point). PCA looks at that whole table at once and finds a small
        number of "directions" (combinations of wavelengths/wavenumbers
        that tend to rise and fall together) that capture most of how the
        batch actually varies. Instead of describing each spectrum by its
        hundreds of individual intensity values, it can now be described
        approximately by just a handful of numbers &mdash; how far along
        each of those directions it sits. Everything below builds on that
        idea.</p>
        <p><strong>The formula:</strong> a standard PCA model is fitted to
        the mean-centered batch: <span class="fm">X<sub>c</sub> =
        T&middot;P<sup>T</sup> + E</span>, where X<sub>c</sub> is the
        batch (n spectra, mean-subtracted), T are the scores (how far each
        spectrum sits along each of the k retained directions), P the
        loadings (the directions themselves &mdash; one loading spectrum
        per retained component), and E the residual (whatever's left over
        once the k directions have been subtracted back out). This is the
        same decomposition used by this app's PCA Scores &amp; Loadings
        and SVD Analysis tools &mdash; QC / Outlier Detection just adds
        the two statistical diagnostics below on top of it, turning
        "distance in PCA space" into an actual pass/fail-style threshold
        instead of a plot you have to eyeball.</p>
    </div>

    <div class="detail">
        <h3>Hotelling T&sup2; and its control limit</h3>
        <p><strong>In plain terms:</strong> T&sup2; asks "how far out
        along the directions the model actually cares about does this
        spectrum sit, relative to how much spread is normal along each of
        those directions?" A direction the batch naturally varies a lot
        along (large &lambda;<sub>j</sub>) can tolerate a big score there
        without being unusual; a direction the batch barely varies along
        at all makes even a modest score there stand out. T&sup2; adds all
        of that up across every retained direction into one number per
        spectrum &mdash; it's conceptually the same idea as a
        multi-dimensional version of a z-score (how many "standard
        deviations out" a point is), just generalized from one dimension
        to k at once.</p>
        <p><strong>The formula:</strong> <span class="fm">T&sup2;<sub>i</sub>
        = &sum;<sub>j=1..k</sub> t<sub>ij</sub>&sup2; /
        &lambda;<sub>j</sub></span> &mdash; the sum, over every retained
        component j, of spectrum i's score t<sub>ij</sub> squared, divided
        by that component's variance &lambda;<sub>j</sub> (its eigenvalue
        &mdash; how much of the batch's total spread that direction
        accounts for). Dividing by &lambda;<sub>j</sub> is exactly what
        makes this a relative, standardized measure rather than a raw
        distance.</p>
        <p>The <strong>control limit</strong> is the T&sup2; value a
        perfectly normal spectrum would only exceed with probability
        &alpha; (the (100&minus;confidence)% you set, e.g. 5% at 95%
        confidence) by chance alone &mdash; the same idea as the control
        limits on a manufacturing control chart. It uses the exact
        F-distribution relationship (Jackson, 1991 &mdash; see
        <a href="#references">References</a>):
        <span class="fm">T&sup2;<sub>lim</sub> = k(n&minus;1)/(n&minus;k)
        &middot; F<sub>&alpha;</sub>(k, n&minus;k)</span>, where
        F<sub>&alpha;</sub>(k, n&minus;k) is the upper-&alpha; critical
        value of the F-distribution with k and (n&minus;k) degrees of
        freedom &mdash; this exact relationship holds because T&sup2; built
        from PCA scores this way is a known, exact rescaling of an
        F-distributed quantity, unlike Q below.</p>
    </div>

    <div class="detail">
        <h3>Q-residual (SPE) and its control limit</h3>
        <p><strong>In plain terms:</strong> Q asks a different question
        from T&sup2; &mdash; not "is this spectrum unusual along the
        directions the model already knows about," but "does this
        spectrum's overall SHAPE even fit the kind of shapes this model
        knows how to describe at all?" Take a spectrum, reconstruct it
        using only the k retained directions (i.e. approximate it as a
        combination of the "typical" shapes the batch shares), and
        subtract that reconstruction from the real spectrum. Whatever's
        left over &mdash; the part the model's directions simply can't
        represent, no matter how they're combined &mdash; is the residual.
        A sharp spike, a baseline artifact, or a genuinely different
        sample all tend to leave a large residual, because those things
        don't look like the shared shape variation the rest of the batch
        was built from.</p>
        <p><strong>The formula:</strong> <span class="fm">Q<sub>i</sub> =
        &Vert;x<sub>i</sub> &minus; &#x0177;<sub>i</sub>&Vert;&sup2;</span>
        &mdash; the squared length (sum of squared differences, point by
        point across the whole spectrum) between spectrum i
        (x<sub>i</sub>) and its reconstruction from the retained
        components (&#x0177;<sub>i</sub>). Squaring and summing means Q
        can't be negative and treats a deviation spread across many points
        the same as one concentrated in a few, in proportion to its total
        size.</p>
        <p>Unlike T&sup2;, Q generally does <em>not</em> follow a known
        textbook distribution (chi-squared or otherwise), so an exact
        control limit formula isn't available. Instead, the
        <strong>control limit</strong> uses the Jackson-Mudholkar (1979)
        approximation (see <a href="#references">References</a>), which
        estimates it from the eigenvalues of the DISCARDED components
        (&theta;<sub>1</sub>, &theta;<sub>2</sub>, &theta;<sub>3</sub>
        &mdash; the 1st, 2nd, and 3rd power sums of the eigenvalues NOT
        retained by the model) combined with the same confidence level
        &alpha; used for T&sup2;. Intuitively: the size of whatever
        variation was left out of the model tells you, statistically, how
        big a "normal" residual should be expected to be &mdash; a model
        that discarded a lot of real variation should tolerate a bigger Q
        before flagging something, and vice versa. This is the standard
        approach throughout multivariate statistical process control.</p>
    </div>

    <div class="detail">
        <a name="det-nonrobust"></a>
        <h3>Why a very extreme outlier can leak into both diagnostics</h3>
        <p>Ordinary PCA (used here, same as this app's other PCA/SVD
        tools) is fitted from ALL the spectra you selected, including any
        outliers among them &mdash; it is not "robust" in the statistical
        sense of automatically ignoring extreme points while fitting the
        model. A very extreme spectrum can therefore pull the model's own
        components toward itself, which can make it show up on BOTH
        T&sup2; and Q even when it's really just one kind of problem.
        This doesn't make either diagnostic wrong, but it's worth knowing
        the model isn't immune to the very thing it's trying to detect.
        If you suspect this is happening, re-run the check with the most
        obviously bad spectra excluded and see whether the remaining
        flags change.</p>
    </div>

    <hr>
    <h2 id="tutorial">Try it yourself &mdash; bundled demo dataset</h2>
    <p><em>File: QC — spectral batch with planted outliers demo.</em> 30
    spectra of the same band with normal batch-to-batch variation, plus 3
    deliberately planted problem spectra: one with an extreme
    concentration (should flag on T&sup2;), one with an added spike
    artifact (should flag on Q), and one with both problems at once.
    Open it from <strong>Help &rarr; Test datasets &rarr;
    Synthetic</strong> &mdash; it imports straight into the
    application.</p>
    <ol>
        <li>Load the dataset and select all 33 spectra.</li>
        <li>Open <strong>QC / Outlier Detection</strong>. Leave
            Auto-select components and 95% confidence at their
            defaults.</li>
        <li>Click <strong>Run QC Check</strong>.</li>
        <li>Expected result: exactly 3 spectra flagged &mdash; look for
            the labels starting with <span class="fm">PLANTED_</span> at
            the top of the (worst-first) results table. The
            concentration one flags mainly on T&sup2;, the spike one
            flags on Q, and the combined one flags on both.</li>
        <li>Select the <span class="fm">PLANTED_Q_spike</span> row and
            switch the View dropdown to <strong>Residual
            spectrum</strong> &mdash; the planted spike shows up as a
            sharp, localized residual right where it was added, while
            the rest of the spectrum matches the model closely.</li>
    </ol>
    <div class="tip">The dataset's <span class="fm">Info</span> sheet
    explains the simulated backstory and exact expected numbers &mdash;
    open the file itself via <strong>Help &rarr; Test datasets &rarr;
    Open datasets folder&hellip;</strong> if you want more detail, but
    everything needed to run this walkthrough is already on this
    page.</div>

    <hr>
    <h2 id="caveats">Caveats</h2>
    <div class="warn">
    <ul>
        <li><strong>A flag is a prompt to look, not a verdict.</strong>
            At 95% confidence, roughly 1 in 20 perfectly normal spectra
            will cross a control limit by chance alone. Always look at
            the actual spectrum (via the Residual spectrum view) before
            deciding it's really a problem.</li>
        <li><strong>PCA here isn't robust</strong> &mdash; see
            <a href="#det-nonrobust">algorithm details</a>. A handful of
            genuinely bad spectra in a small batch can distort the model
            itself, not just their own scores.</li>
        <li><strong>This tool compares spectra to EACH OTHER, not to any
            external standard.</strong> If every spectrum in your
            selection shares the same problem (e.g. they were all
            recorded on a badly calibrated instrument), nothing will be
            flagged &mdash; there's nothing in the batch for the bad ones
            to look unusual against.</li>
        <li><strong>Needs a real batch to compare against.</strong> At
            least 5 spectra are required, and results get more reliable
            with more &mdash; a handful of spectra don't define "normal"
            variation very precisely.</li>
    </ul>
    </div>

    <hr>
    <h2 id="references">References</h2>
    <p style="font-size: 12px;">
    Jackson, J. E. (1991). <em>A User's Guide to Principal Components</em>.
    John Wiley &amp; Sons, New York. (Hotelling T&sup2; control limit,
    Chapter 1.)
    <br><br>
    Jackson, J. E., &amp; Mudholkar, G. S. (1979). Control Procedures for
    Residuals Associated With Principal Component Analysis.
    <em>Technometrics</em>, 21(3), 341&ndash;349.
    (Q-residual/SPE control limit approximation.)
    <br><br>
    Hotelling, H. (1931). The Generalization of Student's Ratio.
    <em>The Annals of Mathematical Statistics</em>, 2(3), 360&ndash;378.
    (Origin of the T&sup2; statistic.)
    </p>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
