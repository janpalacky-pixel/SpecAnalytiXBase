# src/help/kinetics_fitting_help.py


def get_kinetics_fitting_help_title():
    return 'Kinetics Fitting — help'


def get_kinetics_fitting_help_content():
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

    <h1>Kinetics Fitting</h1>

    <p>Fits a time-course of spectra to a sum of exponential decays/growths
    &mdash; either at <strong>one fixed wavelength</strong> (the classic
    single-trace kinetics fit), or as a <strong>global analysis</strong>
    that fits ONE shared set of rate constants across the ENTIRE
    wavelength range at once, producing Decay-Associated Spectra (DAS).
    This is a read-only analysis tool: it never adds, removes, or
    transforms spectral data, so there's no Apply/Add as New step and
    nothing is written to Operations History.</p>

    <div class="tip">New to this tool? Jump straight to
    <a href="#tutorial">Try it yourself &mdash; bundled demo datasets</a>
    for a guided walkthrough with a known right answer.</div>

    <hr>
    <h2 id="concept">The idea</h2>
    <p>You have a series of spectra measured at different times &mdash;
    a reaction progressing, a species decaying, a sample relaxing back to
    equilibrium, anything whose spectral signal changes systematically
    over time. Two related ways to fit it:</p>
    <ul>
        <li><strong>Single wavelength</strong> &mdash; read the signal
            off ONE wavelength/wavenumber from every spectrum, giving a
            single (time, signal) curve, then fit it to a sum of 1-4
            exponential terms. Simple, fast, and exactly what most
            kinetics software does by default.</li>
        <li><strong>Global analysis</strong> &mdash; instead of picking
            one wavelength, use the WHOLE spectrum at every time point.
            One shared set of rate constants is fitted across every
            wavelength simultaneously; each wavelength gets its own
            amplitude for each shared rate constant. Plotting those
            per-wavelength amplitudes against wavelength gives the
            Decay-Associated Spectra (DAS) &mdash; which spectral
            features belong to which kinetic process. Far more
            statistically powerful than single-wavelength fitting (every
            wavelength's data helps pin down the SAME rate constants),
            and the only way to see which wavelengths actually belong to
            which kinetic step.</li>
    </ul>
    <p>Both need a <strong>time value for every selected spectrum</strong>
    &mdash; which wavelength you eventually fit doesn't change that
    requirement.</p>

    <hr>
    <h2 id="workflow">Workflow</h2>
    <ol>
        <li>Select every spectrum in the time series, then open
            <strong>Kinetics Fitting</strong>. All spectra must share one
            identical x-axis (use <strong>Data Range</strong> with
            linearisation first if they don't) &mdash; required even for
            Single wavelength mode, so switching modes inside the dialog
            never hits a surprise mismatch.</li>
        <li>Check the <strong>Time values</strong> table &mdash; a time is
            guessed for every spectrum from its label (the last number
            found in it), always editable, pasteable from a spreadsheet
            column with Ctrl+V. Fix anything the guess got wrong before
            fitting.</li>
        <li>Choose <strong>Single wavelength</strong> or <strong>Global
            analysis</strong>.</li>
        <li>Single wavelength: set the extraction X. Global analysis: the
            X field instead only controls which wavelength's trace gets
            <em>previewed</em> after the fit &mdash; the fit itself
            already uses every wavelength regardless of this value.</li>
        <li>Set the number of components (1-4) and click
            <strong>Run Fit</strong>.</li>
        <li>Read the diagnostics via the <strong>View</strong> dropdown
            and the component-parameter table below &mdash; <strong>Copy
            to clipboard</strong> or <strong>Export CSV</strong> to take
            them elsewhere.</li>
    </ol>

    <hr>
    <h2 id="settings">Settings</h2>
    <table>
        <tr><th>Setting</th><th>Meaning</th></tr>
        <tr><td>Time values</td><td>One per spectrum, required either way.
            Auto-guessed from each spectrum's label, always editable, and
            pasteable as a column with Ctrl+V. <strong>Revert to
            auto-detected times</strong> discards edits and restores the
            original guesses.</td></tr>
        <tr><td>Extraction/Preview X</td><td>Single wavelength mode: the
            exact x-position the kinetic trace is read from (linear
            interpolation, or an average within the window below).
            Global analysis mode: purely cosmetic &mdash; only changes
            which wavelength's trace the "trace + fit" view shows; the
            actual fit already used the full spectrum. Defaults to
            whichever x-position varies the most across your selected
            spectra &mdash; usually the most informative starting
            point.</td></tr>
        <tr><td>Averaging window</td><td>Single wavelength mode only. 0
            reads exactly one interpolated point; a positive value
            averages every point within &plusmn;window of the extraction
            X instead, reducing noise at the cost of some spectral
            resolution.</td></tr>
        <tr><td>Number of components</td><td>1-4 exponential terms.
            Picked manually (unlike PLS's automatic cross-validated
            choice) &mdash; see
            <a href="#det-components">algorithm details</a> for why, and
            how to judge the right number yourself from R²/RMSD and the
            residual plot.</td></tr>
    </table>

    <hr>
    <h2 id="reading-results">Reading the results</h2>

    <h3>View dropdown (plot)</h3>
    <table>
        <tr><th>View</th><th>Shows</th></tr>
        <tr><td>Kinetic trace + fit</td><td>Data points and the total
            fitted curve vs. time, with a residuals panel underneath.
            Global analysis mode: at whichever wavelength the Preview X
            is currently set to.</td></tr>
        <tr><td>Individual components (single wavelength)</td><td>The
            fit decomposed into its separate exponential terms plus the
            offset &mdash; which component dominates early vs. late in
            the trace.</td></tr>
        <tr><td>Decay-Associated Spectra / DAS (global analysis)</td><td>
            Each shared component's amplitude plotted across the WHOLE
            wavelength range, plus the offset spectrum if present &mdash;
            this is the actual payoff of running a global fit instead of
            a single-wavelength one: which spectral features belong to
            which kinetic process.</td></tr>
    </table>

    <h3>Results table</h3>
    <p>One row per fitted component (not per spectrum) &mdash; rate
    constant <span class="fm">k</span>, its standard error, the
    corresponding time constant <span class="fm">&tau; = 1/k</span>, and
    (single wavelength mode only) that component's amplitude at the
    extraction wavelength. Components are always listed
    <strong>slowest first</strong> (smallest k), regardless of the order
    they happened to converge in. Single wavelength mode adds a final
    "Offset (y&infin;)" row for the fitted constant/infinite-time
    asymptote.</p>

    <hr>
    <h2 id="technical">Technical details</h2>

    <div class="detail">
        <h3>The model</h3>
        <p>Single wavelength: <span class="fm">y(t) = y&infin; + &sum;
        A<sub>i</sub>&middot;exp(&minus;k<sub>i</sub>&middot;t)</span>.
        A genuinely RISING signal is still represented this way, with a
        <em>negative</em> amplitude &mdash; rate (how fast) and direction
        (rise vs. decay) are kept as separate, independently
        interpretable numbers rather than folded into the sign of
        k.</p>
        <p>Global analysis: <span class="fm">D(t,&lambda;) = y&infin;
        (&lambda;) + &sum; A<sub>i</sub>(&lambda;)&middot;exp(&minus;k<sub>i</sub>
        &middot;t)</span> &mdash; the SAME k<sub>i</sub> for every
        wavelength &lambda;, but each wavelength gets its own amplitude
        (and its own offset).</p>
    </div>

    <div class="detail">
        <h3>Global analysis via variable projection</h3>
        <p>For any trial set of rate constants, every amplitude
        A<sub>i</sub>(&lambda;) (and offset) is a LINEAR parameter &mdash;
        solvable in one ordinary least-squares step for every wavelength
        at once, given those rate constants. Only the rate constants
        themselves need an iterative nonlinear optimizer, and there are
        only 1-4 of them no matter how many time points or wavelengths
        are in the data. This "variable projection" (Golub-Pereyra)
        approach is the standard method dedicated global/target analysis
        software (Glotaran, TIMP, and similar) uses for exactly this
        problem &mdash; far more stable, and far cheaper, than throwing
        every per-wavelength amplitude into one giant simultaneous
        nonlinear fit alongside the rate constants.</p>
    </div>

    <div class="detail">
        <a name="det-components"></a>
        <h3>Why component count isn't chosen automatically</h3>
        <p>PLS picks its component count via cross-validation because
        the question there ("does this many components predict NEW
        spectra better?") has a clean, well-defined answer from held-out
        data. A kinetics fit doesn't have an equivalent natural
        cross-validation framing &mdash; the question is closer to "does
        the underlying chemistry/physics actually have this many
        distinguishable rate processes", which cross-validation on the
        same curve can't answer. Judge it yourself: increase the
        component count only while R² keeps improving meaningfully and
        the residual plot still shows real structure (not just noise);
        once residuals look like pure noise and an extra component barely
        moves R², you've very likely already got one component too many
        &mdash; check whether two fitted rate constants have become
        implausibly close together (a classic sign of a spurious extra
        component splitting one real process into two numerically
        indistinguishable pieces) or the fit's standard errors have blown
        up.</p>
        <p>Initial rate-constant guesses are seeded automatically,
        log-spaced from roughly 5/duration (a process ~95% done by the
        last time point) to 1/(5&middot;dt) (barely distinguishable from
        instantaneous at the data's own time resolution, using the
        MEDIAN spacing between time points rather than the smallest gap
        &mdash; a single accidentally-close pair of time points
        shouldn't be allowed to dictate an unrealistic fast-end
        guess).</p>
    </div>

    <hr>
    <h2 id="tutorial">Try it yourself &mdash; bundled demo datasets</h2>
    <p>Two ready-made example workbooks are shipped with the app, one per
    mode, each with a known right answer. Open them from <strong>Help
    &rarr; Test datasets &rarr; Synthetic</strong> &mdash; each imports
    straight into the application.</p>

    <h3>1. Single wavelength: "single-exponential decay" demo</h3>
    <p><em>File: Kinetics — single-exponential decay demo.</em> 20 spectra
    of a species decaying away with one clean exponential process.</p>
    <ol>
        <li>Load the dataset, select all 20 spectra, open <strong>Kinetics
            Fitting</strong>.</li>
        <li>Leave mode on <strong>Single wavelength</strong>. Time values
            are auto-guessed correctly from the labels &mdash; no editing
            needed.</li>
        <li>Set Extraction X to <strong>550</strong> (the peak of the
            decaying band) and Number of components to <strong>1</strong>.</li>
        <li>Click <strong>Run Fit</strong>.</li>
        <li>Expected result: rate constant k &asymp; 0.20 (&tau; &asymp; 5),
            R² above 0.99.</li>
    </ol>

    <h3>2. Global analysis: "two-step consecutive reaction" demo</h3>
    <p><em>File: Kinetics — global analysis two-step demo.</em> 18 spectra
    of a two-step process (A &rarr; B &rarr; C) with two well-separated
    rate constants and distinct, overlapping spectral signatures for each
    step.</p>
    <ol>
        <li>Load the dataset, select all 18 spectra, open <strong>Kinetics
            Fitting</strong>.</li>
        <li>Choose <strong>Global analysis</strong>. Time values are
            auto-guessed correctly &mdash; no editing needed.</li>
        <li>Set Number of components to <strong>2</strong> and click
            <strong>Run Fit</strong>.</li>
        <li>Expected result: rate constants near <strong>k &asymp;
            0.08</strong> and <strong>k &asymp; 0.5</strong> (&tau;
            &asymp; 12.5 and &asymp; 2), R² above 0.99. Switch the View
            dropdown to <strong>Decay-Associated Spectra</strong> to see
            each step's own spectral signature.</li>
    </ol>
    <div class="tip">Both workbooks' <span class="fm">Info</span> sheet
    explains the simulated backstory and exact expected numbers &mdash;
    open the file itself via <strong>Help &rarr; Test datasets &rarr;
    Open datasets folder&hellip;</strong> if you want more detail, but
    everything needed to run this walkthrough is already on this
    page.</div>

    <hr>
    <h2 id="caveats">Caveats</h2>
    <div class="warn">
    <ul>
        <li><strong>Global analysis assumes the SAME rate constants apply
            to every wavelength.</strong> That's a real modeling
            assumption, not automatically true &mdash; it holds for a
            genuine sequence of first-order/pseudo-first-order steps, but
            not for a system where different wavelengths track physically
            unrelated processes. A poor global fit (versus good
            single-wavelength fits at individual wavelengths) is itself
            evidence the assumption doesn't hold here.</li>
        <li><strong>Your data must actually cover the relevant
            timescale.</strong> A rate constant whose 1/k is much longer
            than your last time point, or much shorter than your first
            interval, is poorly constrained by the data no matter how
            good the fit looks &mdash; check the standard error, not just
            R².</li>
        <li><strong>Time units are whatever you entered.</strong> The
            fitted k / &tau; are in the reciprocal / same units as your
            Time column &mdash; seconds in, per-second k out; minutes in,
            per-minute k out. Keep it consistent across every spectrum in
            one fit.</li>
        <li><strong>More components almost always fits better on the
            calibration data itself</strong> &mdash; that's exactly why
            component count isn't picked automatically here (see
            <a href="#det-components">algorithm details</a>). A model
            that fits beautifully but reports two implausibly similar
            rate constants, or huge standard errors, is telling you it
            has one component too many.</li>
    </ul>
    </div>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
