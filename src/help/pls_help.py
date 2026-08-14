# src/help/pls_help.py


def get_pls_help_title():
    return 'PLS / PLS-DA — help'


def get_pls_help_content():
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
        </style>
    </head>
    <body>
    <a name="top"></a>

    <h1>PLS / PLS-DA</h1>

    <p>Builds a calibration model relating a set of spectra to a known
    property of each one &mdash; a continuous quantity like concentration
    (<strong>PLS Regression</strong>) or a category like sample type
    (<strong>PLS-DA</strong>, classification) &mdash; then uses that model
    to read the same property off of new, unlabeled spectra. This is a
    read-only analysis tool: it never adds, removes, or transforms
    spectral data, so there's no Apply/Add as New step and nothing is
    written to Operations History.</p>

    <div class="tip">New to this tool? Jump straight to
    <a href="#tutorial">Try it yourself &mdash; bundled demo datasets</a>
    for a guided walkthrough with a known right answer.</div>

    <hr>
    <h2 id="concept">The idea</h2>
    <p>Two related tasks, same underlying algorithm:</p>
    <ul>
        <li><strong>PLS Regression</strong> &mdash; you know the
            concentration (or other numeric quantity) of a set of
            standards. The model learns how the whole spectral shape
            correlates with that quantity, then predicts it for any new
            spectrum &mdash; a quantitative calibration curve, but using
            the full spectrum instead of one peak's height.</li>
        <li><strong>PLS-DA</strong> &mdash; you know the class (species,
            batch, treatment group, ...) of a set of reference spectra.
            The model learns to tell the classes apart, then classifies
            any new spectrum &mdash; useful when no single band cleanly
            distinguishes the groups but the overall spectral shape does.</li>
    </ul>
    <p>Both need <strong>calibration spectra</strong> &mdash; ones where
    you already know the right answer &mdash; to build the model in the
    first place. Any additional spectra you select without a known value
    are treated as <strong>unknowns</strong>: the model predicts them but
    they never influence how the model itself is built.</p>

    <hr>
    <h2 id="workflow">Workflow</h2>
    <ol>
        <li>Select every spectrum you want involved &mdash; both your
            calibration standards AND any unknowns you want predicted
            &mdash; then open PLS / PLS-DA. All must share one identical
            x-axis (use <strong>Data Range</strong> with linearisation
            first if they don't).</li>
        <li>Choose <strong>PLS Regression</strong> or <strong>PLS-DA</strong>
            at the top.</li>
        <li>In the calibration table, enter the known value (a number for
            Regression, a class name for PLS-DA) next to every calibration
            spectrum. <strong>Leave the row blank for any spectrum you
            want treated as an unknown.</strong> You can paste a column
            of values directly from a spreadsheet.</li>
        <li>Adjust settings if needed (see below), then click
            <strong>Run PLS</strong>.</li>
        <li>Read the diagnostics (cross-validation curve, scores,
            fit quality, coefficients) via the <strong>View</strong>
            dropdown, and the per-spectrum predictions in the results
            table below &mdash; <strong>Copy to clipboard</strong> or
            <strong>Export CSV</strong> to take them elsewhere.</li>
    </ol>

    <div class="warn">
        <strong>Needs a real calibration set.</strong> At least 4
        calibration spectra are required just to run at all, and that's
        a bare technical minimum, not a recommendation &mdash; a
        trustworthy model typically needs considerably more, spanning
        the full range of values/classes you expect to see in practice.
        Too few standards, or standards that don't cover your expected
        range, will fit numbers without producing a model you can trust
        on new samples.
    </div>

    <hr>
    <h2 id="tutorial">Try it yourself &mdash; bundled demo datasets</h2>
    <p>New to PLS? Two ready-made example workbooks are shipped with the
    app, purpose-built so you can run through the whole workflow once with
    a known right answer before trying it on your own data. Open them from
    <strong>Help &rarr; Test datasets &rarr; Synthetic</strong> &mdash; each
    one imports straight into the application. (Both walkthroughs below
    assume this dialog's own <strong>Shorten Names</strong> checkbox is
    ticked, so the calibration table shows short labels like
    <span class="fm">cal_01</span> instead of the full
    <span class="fm">filename : cal_01</span> &mdash; it's a separate
    checkbox from the main window's and starts unticked, so tick it in
    this dialog if your rows look longer than that.)</p>

    <h3>1. PLS Regression: "protein concentration" demo</h3>
    <p><em>File: PLS regression &mdash; protein concentration demo.</em>
    Simulates a UV absorbance calibration: 15 samples of known protein
    concentration, plus 5 unknowns to predict.</p>
    <ol>
        <li>Load the dataset (adds 20 spectra), select all of them, and
            open <strong>PLS / PLS-DA</strong>.</li>
        <li>Choose <strong>Regression</strong>.</li>
        <li>Rows in the calibration table run <span class="fm">cal_01</span>
            &hellip; <span class="fm">cal_15</span>, then
            <span class="fm">unknown_A</span> &hellip;
            <span class="fm">unknown_E</span>. Click the Calibration value
            cell next to <span class="fm">cal_01</span> and paste this
            whole block (select it, Ctrl+C, click the cell, Ctrl+V) &mdash;
            it fills all 15 rows down in order automatically:
<pre style="background:#282c34; color:#abb2bf; padding:10px 14px; border-radius:4px; overflow-x:auto;">0.1
0.236
0.371
0.507
0.643
0.779
0.914
1.05
1.186
1.321
1.457
1.593
1.729
1.864
2.0</pre>
            Leave the five <span class="fm">unknown_A</span> &hellip;
            <span class="fm">unknown_E</span> rows below that blank.</li>
        <li>Click <strong>Run PLS</strong>. The results table now shows a
            predicted concentration for each unknown.</li>
        <li>Check your 5 predictions against the true values below. They
            should land close, though not exactly on top of, these numbers
            &mdash; the dataset has a deliberate, unrelated source of
            variation mixed in on purpose, so this isn't a trivially
            perfect fit:
            <table>
                <tr><th>Spectrum</th><th>True value</th><th>You should get roughly</th></tr>
                <tr><td class="fm">unknown_A</td><td>0.35</td><td>~0.32</td></tr>
                <tr><td class="fm">unknown_B</td><td>1.62</td><td>~1.60</td></tr>
                <tr><td class="fm">unknown_C</td><td>0.88</td><td>~0.90</td></tr>
                <tr><td class="fm">unknown_D</td><td>1.15</td><td>~1.14</td></tr>
                <tr><td class="fm">unknown_E</td><td>0.55</td><td>~0.54</td></tr>
            </table>
            Close to these = it worked. Wildly different = something's
            wrong with the run (wrong mode, values in the wrong rows,
            wrong x-axis on the selected spectra, etc.).</li>
    </ol>

    <h3>2. PLS-DA: "sample type A/B" demo</h3>
    <p><em>File: PLS-DA classification &mdash; sample type A/B demo.</em>
    Simulates two visually-similar-but-distinguishable sample types: 10
    reference spectra of each type, plus 4 unknowns to classify.</p>
    <ol>
        <li>Load the dataset (adds 24 spectra), select all of them, and
            open <strong>PLS / PLS-DA</strong>.</li>
        <li>Choose <strong>Classification</strong>.</li>
        <li>Rows run <span class="fm">classA_01</span> &hellip;
            <span class="fm">classA_10</span>, then
            <span class="fm">classB_01</span> &hellip;
            <span class="fm">classB_10</span>, then
            <span class="fm">unknown_1</span> &hellip;
            <span class="fm">unknown_4</span>. Click the Calibration value
            cell next to <span class="fm">classA_01</span> and paste this
            block &mdash; it covers all 20 calibration rows in order:
<pre style="background:#282c34; color:#abb2bf; padding:10px 14px; border-radius:4px; overflow-x:auto;">A
A
A
A
A
A
A
A
A
A
B
B
B
B
B
B
B
B
B
B</pre>
            Leave the four <span class="fm">unknown_1</span> &hellip;
            <span class="fm">unknown_4</span> rows below that blank.</li>
        <li>Click <strong>Run PLS</strong>, then check the predicted class
            for each unknown in the results table.</li>
        <li>Correct result: <span class="fm">unknown_1 = A</span>,
            <span class="fm">unknown_2 = B</span>,
            <span class="fm">unknown_3 = A</span>,
            <span class="fm">unknown_4 = B</span> &mdash; on this dataset
            the classes are cleanly separable, so a correctly-run model
            gets all four right with high confidence (class score close to
            1.0 for the winning class).</li>
    </ol>
    <div class="tip">Both workbooks also ship a <span class="fm">Calibration_values</span>
    sheet (the same numbers as above, laid out with spectrum names) and an
    <span class="fm">Info</span> sheet with the full backstory &mdash;
    open the file itself via <strong>Help &rarr; Test datasets &rarr; Open
    datasets folder&hellip;</strong> if you want to see them, but you don't
    need to: everything required to run this walkthrough is already on
    this page.</div>

    <hr>
    <h2 id="settings">Settings</h2>
    <table>
        <tr><th>Setting</th><th>Meaning</th></tr>
        <tr><td>Number of components</td><td><strong>Auto</strong>
            (recommended) picks the number of latent variables
            automatically from cross-validation (see
            <a href="#det-components">algorithm details</a>); switch it off
            to force a specific number instead &mdash; useful for comparing
            models or matching a value from other software.</td></tr>
        <tr><td>CV folds</td><td>0 uses leave-one-out (each calibration
            spectrum held out and predicted one at a time &mdash; used
            automatically for small calibration sets regardless of this
            setting); a positive number uses that many folds of k-fold
            cross-validation instead.</td></tr>
        <tr><td>Autoscale X</td><td>Standardizes each wavelength channel to
            unit variance before fitting (in addition to the mean-centering
            PLS always does internally). Recommended when different parts
            of the spectrum have very different intensity scales.</td></tr>
    </table>

    <hr>
    <h2 id="reading-results">Reading the results</h2>

    <h3>View dropdown (plot)</h3>
    <table>
        <tr><th>View</th><th>Shows</th></tr>
        <tr><td>Cross-validation curve</td><td>RMSECV (Regression) or CV
            accuracy (PLS-DA) at every candidate component count, with the
            automatically chosen one marked.</td></tr>
        <tr><td>Scores</td><td>Calibration spectra projected onto the
            first two components &mdash; colour shows the calibration
            value (Regression) or class (PLS-DA). Spectra that cluster
            tightly by colour indicate the model is picking up a real,
            consistent signal.</td></tr>
        <tr><td>Fit quality</td><td>Actual vs predicted scatter with R²
            (Regression), or a confusion matrix with overall accuracy
            (PLS-DA) &mdash; both computed on the calibration set.</td></tr>
        <tr><td>Coefficients &amp; VIP</td><td>The model's regression
            coefficient at every wavelength (which direction and how
            strongly each point pushes the prediction), and VIP
            (Variable Importance in Projection, conventionally
            &ge;&nbsp;1 = more influential than an average variable)
            &mdash; both plotted against the spectrum's own x-axis, so you
            can see which spectral regions the model actually relies
            on. <a class="det-link" href="#det-vip">algorithm details</a></td></tr>
    </table>

    <h3>Results table</h3>
    <p>One row per spectrum you selected &mdash; both calibration and
    unknowns. <strong>Role</strong> distinguishes which is which.
    Regression rows show Actual/Predicted/Residual (Actual is blank for
    unknowns, since there's nothing to compare against). PLS-DA rows show
    the actual and predicted class, whether the calibration prediction was
    correct, and a probability-like score for every possible class &mdash;
    for an unknown, the predicted class is simply whichever score is
    highest.</p>

    <hr>
    <h2 id="technical">Technical details</h2>

    <div class="detail">
        <a name="det-components"></a>
        <h3>Choosing the number of components</h3>
        <p>Too few components underfits (the model misses real signal);
        too many overfits (it starts fitting noise, and looks great on the
        calibration set but predicts poorly on new spectra). Cross-validation
        estimates how well each candidate component count generalizes by
        repeatedly holding out part of the calibration set, fitting on the
        rest, and scoring the held-out predictions.</p>
        <p><strong>Auto mode doesn't simply take the single best-scoring
        component count</strong> &mdash; on real (noisy) data the
        cross-validation curve is very often almost flat past some point,
        and picking the literal numerical minimum/maximum there means
        picking an arbitrarily larger, harder-to-interpret model for an
        improvement that's really just noise. Instead, the SIMPLEST model
        within a small tolerance of the best score is chosen (2% relative
        for RMSECV, 1 percentage point for CV accuracy) &mdash; standard
        chemometrics practice, and confirmed directly against synthetic
        data with a known single-component ground truth to correctly
        prefer the small, correct model over a larger one that scored
        negligibly better by chance.</p>
    </div>

    <div class="detail">
        <a name="det-vip"></a>
        <h3>VIP (Variable Importance in Projection)</h3>
        <p>The standard VIP formula (Wold et al.), computed from the
        fitted model's component scores, weights, and y-loadings. A VIP
        score above 1.0 is conventionally read as "more influential on
        the prediction than an average wavelength" &mdash; useful for
        identifying which spectral region actually drives the model,
        separate from the raw regression coefficient (which can be large
        for a noisy, low-importance variable too). If VIP can't be
        computed for a particular model (rare shape edge cases), it's
        simply omitted from the plot rather than failing the whole
        analysis &mdash; the coefficient curve is always shown regardless.</p>
    </div>

    <div class="detail">
        <h3>PLS-DA via dummy-coded regression</h3>
        <p>PLS-DA is implemented as standard PLS regression against a
        one-hot ("dummy") encoded class matrix &mdash; one column per
        class, 1.0 for a sample's own class and 0.0 for every other
        &mdash; the classic, widely-used approach. A new spectrum is
        classified by whichever class's predicted column comes out
        highest; the other columns' values are shown in the results
        table as a rough indication of how close a call it was (a
        near-tie between two classes is a genuinely ambiguous
        prediction, not a confident one, even though a single class
        is still reported).</p>
    </div>

    <hr>
    <h2 id="caveats">Caveats</h2>
    <div class="warn">
    <ul>
        <li><strong>A model only extrapolates as far as its calibration
            set covers.</strong> A concentration prediction well outside
            the range of your standards, or a spectrum genuinely unlike
            anything in the calibration set, should be treated with real
            skepticism &mdash; the model has no way to know it's being
            asked to extrapolate.</li>
        <li><strong>Correlation in the calibration set isn't necessarily
            the property you care about.</strong> If every high-concentration
            standard was also measured on a different day, with a different
            instrument drift, etc., the model may partly be learning that
            confound instead of the concentration itself. Randomize/balance
            calibration conditions where practical.</li>
        <li><strong>Calibration accuracy is optimistic; cross-validated
            accuracy is the honest estimate.</strong> Always look at
            RMSECV / CV accuracy, not just RMSEC / calibration accuracy,
            when judging how well the model will really perform on new
            spectra.</li>
    </ul>
    </div>

    <hr>
    <h2 id="references">References</h2>
    <p style="font-size: 12px;">
    Wold, S., Sj&ouml;str&ouml;m, M., &amp; Eriksson, L. (2001). PLS-regression:
    a basic tool of chemometrics. <em>Chemometrics and Intelligent
    Laboratory Systems</em>, 58(2), 109&ndash;130. (PLS/PLS-DA and the
    NIPALS-style algorithm this tool implements.)
    <br><br>
    Wold, S., Johansson, E., &amp; Cocchi, M. (1993). PLS &mdash; partial
    least-squares projections to latent structures. In H. Kubinyi (Ed.),
    <em>3D QSAR in Drug Design</em> (pp. 523&ndash;550). ESCOM, Leiden.
    (Origin of the VIP &mdash; Variable Importance in Projection &mdash;
    statistic used in this dialog's coefficients/VIP view.)
    </p>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
