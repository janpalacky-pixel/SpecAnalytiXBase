# src/help/automated_baseline_help.py

def get_automated_baseline_help_title():
    """Return the title for automated baseline correction help."""
    return "Automated Baseline Correction Help"

def get_automated_baseline_help_content():
    """Return HTML content for the help."""
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1, h2, h3 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { font-size: 1.1em; border-bottom: 1px solid #ccc; }
            .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; }
            .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace;}
        </style>
    </head>
    <body>
        <h1>Automated Baseline Correction Help</h1>
        
        <h2>Overview</h2>
        <p>This tool offers three automated curve-fitting algorithms for detecting and removing curving baselines, chosen with the <b>Baseline Method</b> dropdown: <b>ALS</b> (Asymmetric Least Squares), <b>airPLS</b> (adaptive iteratively reweighted Penalized Least Squares), and <b>arPLS</b> (asymmetrically reweighted Penalized Least Squares). All three are enhanced with <b>region-specific fitting</b>, letting you define which parts of the spectrum the algorithm should use for its calculation — including one-click <b>Region Shortcuts</b> (e.g. the water/O-H band) that add straight into the same ranges table.</p>

        <div class="warning">
            <strong>Baseline-correct first — don't skip this if you're heading into NMF or MCR-ALS.</strong>
            An uncorrected fluorescence/offset background can dominate a spectrum so completely that
            downstream non-negative decompositions (NMF, MCR-ALS, and their 2D Map spatial-map modes)
            become numerically unstable — see those tools' own help for why. Either algorithm here is
            fine for that purpose; it doesn't need to be a perfect fit, just a reasonable one.
        </div>

        <h2>Workflow</h2>
        <ol>
            <li>Select a spectrum from the list on the left to preview it.</li>
            <li>Pick a <b>Baseline Method</b>: ALS, airPLS, or arPLS (see below for the difference).</li>
            <li>Define the regions for the baseline calculation using one of the two modes below —
                optionally start from a <b>Region Shortcut</b> checkbox (e.g. the water band, for
                aqueous/biological samples) and add or adjust ranges from there.</li>
            <li>Adjust the method's parameters to fine-tune the fit.</li>
            <li>Observe the real-time preview to ensure the baseline is correct.</li>
            <li>Click <b>Apply</b> to replace the selected spectra with the corrected result, or
                <b>Add as New</b> to keep the originals untouched and add the result under new names.</li>
        </ol>

        <h3>ALS vs. airPLS vs. arPLS — which one?</h3>
        <div class="tip">
            <p><b>ALS</b> is the more predictable default: its <b>Smoothness (λ)</b> and <b>Asymmetry (p)</b>
            sliders give direct, independent control, and it tends to be forgiving of a wide range of
            λ values. Start here if you're not sure.</p>
            <p><b>airPLS</b> needs no asymmetry parameter — it derives its weighting adaptively from the
            fit residuals at each iteration — which can make it a faster one-slider fit once you've found
            a good λ for your instrument's pixel count. It typically needs a <em>much smaller</em> λ than
            ALS at a comparable smoothness (its penalty is a first-difference penalty here, versus ALS's
            second-difference/curvature penalty, so the same nominal λ behaves very differently between
            the two). Use the live preview — a λ that's too large for airPLS will flatten out broad,
            genuine background curvature instead of following it.</p>
            <p><b>arPLS</b> also needs no asymmetry parameter, and — unlike airPLS — uses the <em>same</em> second-difference penalty as ALS, so its λ slider sits on ALS's scale, not airPLS's much smaller one. Where it differs from both is the weighting rule: each iteration, every point is re-weighted by a logistic function of how far its residual sits below a data-driven threshold, rather than ALS's fixed asymmetry split or airPLS's exponentially growing weights. This tends to be a little steadier on noisy baselines than airPLS. Worth trying as a second opinion alongside airPLS on the same spectrum — the live preview makes the comparison quick.</p>
        </div>

        <div class="tip">
            <strong>Apply vs. Add as New vs. Close:</strong>
            <ul>
                <li><b>Apply</b> replaces the spectra loaded in the dialog with their corrected result. The
                originals are overwritten once Apply runs.</li>
                <li><b>Add as New</b> leaves the originals completely untouched and adds the corrected
                result to the spectra list under new, unique names (e.g. <code>samplename_baseline_als</code>
                <code>samplename_baseline_airpls</code>, or <code>samplename_baseline_arpls</code> depending on the method used,
                with a number appended if that name is already taken).</li>
                <li><b>Close</b> closes the dialog without applying anything to the main window's spectra.</li>
            </ul>
            <p>There is no separate Run step in the main window for this operation — Apply and Add as New
            commit immediately, with their own confirmation message shown right in the dialog, after which
            the dialog closes automatically. Whatever settings were last shown are still remembered the next
            time you reopen it for the same spectra.</p>
        </div>

        <h3>Fitting Region Modes</h3>
        <div class="tip">
            <h4>Default Mode: Exclude Bad Regions</h4>
            <p>With the "Invert Regions" box <b>unchecked</b>, you draw red boxes over <b>peaks you want to ignore</b>. The algorithm will use all un-shaded areas to calculate the baseline. This is best for spectra with a few isolated peaks on a mostly flat baseline.</p>
            <h4>Recommended Mode for Raman: Include Good Regions</h4>
            <p>With the "Invert Regions" box <b>checked</b>, you draw boxes over the <b>flat valleys that are the true baseline</b>. The algorithm will <b>only</b> use these regions for its calculation and interpolate the baseline between them. This is the most powerful method for complex spectra.</p>
            <h4>Region Shortcuts</h4>
            <p>One-click checkboxes, organized as a <b>tab per category</b> so this panel stays a fixed
            size as more shortcuts are added — currently <b>Raman</b> (Water / O-H stretch,
            2800–3700 cm<sup>-1</sup>) and <b>Biological / Cell Imaging</b> (Silent region,
            1800–2600 cm<sup>-1</sup>; Glass/fused-silica substrate hump, 400–550 cm<sup>-1</sup>;
            CaF<sub>2</sub> substrate peak, 320–325 cm<sup>-1</sup>). The biological-category ranges are
            common candidates from general Raman literature, not measured against any specific instrument
            here — check them against your own excitation wavelength, substrate and sample prep.</p>
            <p>Checking a shortcut adds its range straight into the ranges table above — exactly as if
            you'd dragged that range on the plot yourself, even across different tabs at once. It carries
            <b>no special behavior of its own</b>: once added, a shortcut's region follows <b>Invert
            Regions</b> just like a manually drawn one (so with Invert checked, a shortcut marks a region
            to fit <em>within</em>, not exclude), and checking several at once adds each of their ranges
            (additive). Unchecking a shortcut — or deleting its row directly from the table — removes
            just that range.</p>
        </div>

        <h2>Parameters Explained</h2>
        <h3>ALS</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Controls how stiff or flexible the baseline is. Higher values (e.g., <code>1e7</code>) create a very smooth line for broad backgrounds. Lower values (e.g., <code>1e4</code>) create a more flexible line that can follow local variations.</li>
            <li><b>Asymmetry (p):</b> Controls how much the algorithm penalizes peaks. A value of <code>0.01</code> is a good start. Lower values are for sharp peaks; higher values can be used for broader peaks or noisy data.</li>
        </ul>
        <h3>airPLS</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role as ALS's λ — stiffer (larger) vs. more flexible (smaller) — but on a <em>much smaller</em> numeric scale (the dialog's airPLS slider defaults to <code>200</code>, not <code>1e6</code>). airPLS has no separate asymmetry parameter to tune.</li>
        </ul>
        <h3>arPLS</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role and the <em>same numeric scale</em> as ALS's λ (the dialog's arPLS slider defaults to <code>1e5</code>) — not airPLS's much smaller scale, since arPLS uses the same second-difference penalty ALS does. arPLS has no separate asymmetry parameter to tune.</li>
        </ul>

        <h2>Technical Details</h2>
        <h3>ALS</h3>
        <p>The ALS algorithm iteratively finds a baseline (<code>z</code>) that minimizes the following equation:</p>
        <code>Σw(y - z)² + λΣ(Δ²z)²</code>
        <ul>
            <li>The first term <code>Σw(y - z)²</code> is the "fidelity" term. It tries to keep the baseline <code>z</code> close to the original signal <code>y</code>. The weights <code>w</code> are adjusted at each step based on the asymmetry parameter <code>p</code>, which heavily penalizes points where the signal is above the baseline (i.e., peaks).</li>
            <li>The second term <code>λΣ(Δ²z)²</code> is the "smoothness" penalty. It penalizes curvature in the baseline. The smoothness parameter <code>λ</code> controls how much influence this term has.</li>
        </ul>
        <h3>airPLS</h3>
        <p>airPLS also fits a penalized-least-squares baseline, but derives its point weights <code>w</code>
        <em>adaptively</em> from the fit itself rather than from a fixed asymmetry parameter: at each
        iteration <code>i</code>, any point where the signal sits above the current baseline (a peak) gets
        weight 0, while points below it get a weight that grows with iteration number and residual size
        (<code>w ∝ exp(i·|residual|/Σ|negative residuals|)</code>), pulling the next fit down toward the
        noise floor. Iteration stops once the total negative residual becomes negligible relative to the
        signal, or after a fixed number of iterations.</p>
        <h3>arPLS</h3>
        <p>arPLS fits the same penalized-least-squares equation as ALS (second-difference smoothness penalty), but instead of ALS's fixed asymmetry split, re-weights every point each iteration by a logistic function of how far its residual <code>d</code> sits below a data-driven threshold built from the <em>negative</em> residuals' own mean <code>m</code> and standard deviation <code>s</code>: <code>w = 1 / (1 + exp(2(d - (2s - m)) / s))</code>. Points far below the threshold get a weight near 1 (treated as baseline), points far above it get a weight near 0 (treated as peak), and the transition between the two is smooth rather than airPLS's hard exponential growth. Iteration stops once the weight vector stops changing appreciably between steps, or after a fixed number of iterations.</p>

        <h2>References</h2>
        <ul>
            <li>Eilers, P. H. C., & Boelens, H. F. M. (2005). <i>Baseline Correction with Asymmetric Least Squares Smoothing</i>. Leiden University Medical Centre Report. (ALS)</li>
            <li>Zhang, Z.-M., Chen, S., & Liang, Y.-Z. (2010). <i>Baseline correction using adaptive iteratively reweighted penalized least squares.</i> Analyst, 135(5), 1138–1146. (airPLS)</li>
            <li>Baek, S.-J., Park, A., Ahn, Y.-J., & Choo, J. (2015). <i>Baseline correction using asymmetrically reweighted penalized least squares smoothing.</i> Analyst, 140(1), 250–257. (arPLS)</li>
        </ul>
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