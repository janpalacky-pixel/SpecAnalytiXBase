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
        <p>This tool offers twelve automated curve-fitting algorithms for detecting and removing curving baselines, chosen with the <b>Baseline Method</b> dropdown: <b>ALS</b> (Asymmetric Least Squares), <b>airPLS</b> (adaptive iteratively reweighted Penalized Least Squares), <b>arPLS</b> (asymmetrically reweighted Penalized Least Squares), <b>iarPLS</b> (improved arPLS), <b>asPLS</b> (adaptive smoothness Penalized Least Squares), <b>drPLS</b> (doubly reweighted Penalized Least Squares), <b>psalsa</b> (peaked signal's asymmetric least squares algorithm), <b>I-ModPoly</b> (Improved Modified Polynomial fit), <b>Morphological Opening</b> (adaptive structuring element), <b>mpls</b> (morphological weighted Penalized Least Squares), <b>Morphology + Mollification</b>, <b>mpspline</b> (morphology-based penalized spline), and <b>jbcd</b> (joint baseline-correction and denoising) — the first seven fit a locally-penalized smooth curve built up through iterative reweighting, I-ModPoly instead fits a single global polynomial with iterative peak rejection, Morphological Opening uses neither, estimating the baseline from local minima/maxima with no fitted model at all, mpls combines both ideas with a single non-iterative penalized-least-squares solve through morphology-identified anchor points, Morphology + Mollification combines them a different way — no linear system to solve at all, just repeated min/max operations smoothed by a fixed convolution kernel until the result settles — mpspline combines them yet another way, using morphology to pick out trustworthy points for a non-iterative fit as mpls does, but fitting a compact cubic spline through them instead of mpls's direct Whittaker smoother — and jbcd is the one method here that never singles out anchor points at all, instead solving a single joint equation for a smooth baseline and a denoised spectrum together, pulled toward a morphological opening rather than fit through a handful of points sampled from it. All thirteen are enhanced with <b>region-specific fitting</b>, letting you define which parts of the spectrum the algorithm should use for its calculation — including one-click <b>Region Shortcuts</b> (e.g. the water/O-H band) that add straight into the same ranges table.</p>
        <p>The <b>Baseline Method</b> dropdown groups these thirteen into three families so the list stays easy to scan: <b>ALS / Whittaker-smoothing family</b> (ALS, airPLS, arPLS, iarPLS, asPLS, drPLS, psalsa), <b>Polynomial</b> (I-ModPoly), and <b>Morphological family</b> (Morphological Opening, mpls, Morphology + Mollification, mpspline, jbcd) — click a family heading in the dropdown to expand or collapse it.</p>

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
            <li>Pick a <b>Baseline Method</b> from the grouped dropdown: ALS, airPLS, arPLS, iarPLS, asPLS, drPLS, or psalsa under ALS / Whittaker-smoothing family; I-ModPoly under Polynomial; or Morphological Opening, mpls, Morphology + Mollification, mpspline, or jbcd under Morphological family (see below for the difference).</li>
            <li>Define the regions for the baseline calculation using one of the two modes below —
                optionally start from a <b>Region Shortcut</b> checkbox (e.g. the water band, for
                aqueous/biological samples) and add or adjust ranges from there.</li>
            <li>Adjust the method's parameters to fine-tune the fit.</li>
            <li>Observe the real-time preview to ensure the baseline is correct.</li>
            <li>Click <b>Apply</b> to replace the selected spectra with the corrected result, or
                <b>Add as New</b> to keep the originals untouched and add the result under new names.</li>
        </ol>

        <h3>ALS vs. airPLS vs. arPLS vs. iarPLS vs. asPLS vs. drPLS vs. psalsa vs. I-ModPoly vs. Morphological Opening vs. mpls vs. Morphology + Mollification vs. mpspline vs. jbcd — which one?</h3>
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
            <p><b>iarPLS</b> is a direct refinement of arPLS, on the same λ scale and with the same single slider — it targets one specific known weakness of arPLS: a tendency to overestimate (sit a bit high under) small peaks in noisy data. It reaches that with a different weighting curve that sharpens as iterations proceed instead of arPLS's fixed logistic one. If arPLS's baseline looks like it's cutting into small peaks, try iarPLS on the same λ before reaching for a different method entirely.</p>
            <p><b>asPLS</b> is another arPLS-style refinement, also a single λ slider with no asymmetry parameter, but the change here is structural rather than just a different weighting curve: the smoothness penalty itself is no longer applied uniformly across the spectrum. It adapts point-by-point, automatically, based on how far each point currently sits from the fit — staying stiffer where the fit already looks confident and loosening near features it's still unsure about. Worth trying alongside arPLS/iarPLS on backgrounds where the right smoothness genuinely seems to vary across the spectrum rather than being one fixed value everywhere.</p>
            <p><b>drPLS</b> is the most different of the arPLS-family methods here — it's the only one with a second slider. On top of arPLS's usual smoothness penalty it adds a mild extra penalty against an overall sloped baseline, plus a <b>Peak Relaxation (η)</b> control that lets you dial in how much the smoothness penalty itself relaxes specifically under peak regions, independent of the background elsewhere — something none of the single-λ methods above can do. Worth reaching for when a spectrum has both a background that needs a strong smoothness penalty and peaks that a single λ value can't both smooth correctly and preserve at the same time.</p>
            <p><b>psalsa</b> goes back to ALS's own λ scale and keeps ALS's <b>Asymmetry (p)</b> slider too — but where ALS gives every point above the fit the same fixed weight regardless of how tall it is, psalsa decays that weight exponentially the further above the fit a point sits, so a small bump keeps some influence while a tall peak is suppressed almost immediately. That lets p sit much higher here than ALS typically wants (0.5 is a reasonable starting point, versus ALS's 0.01) while still handling noisy data and real peaks well. Worth trying if ALS feels too all-or-nothing about what counts as a peak.</p>
            <p><b>I-ModPoly</b> is a different kind of method entirely: instead of a locally-penalized smooth curve, it fits one global low-order polynomial (its only parameter is <b>Polynomial Order</b> — no λ, no asymmetry), iteratively rejecting points that look like peaks from the fit. That makes it more predictable on backgrounds that are genuinely polynomial-shaped (e.g. a broad, simple fluorescence curve), and less flexible than ALS/airPLS/arPLS on backgrounds with local structure a fixed polynomial order can't follow. Worth trying when the other three all seem to either chase peaks or miss background curvature — a different fitting family sometimes just suits the data better.</p>
            <p><b>Morphological Opening</b> is the odd one out: no fitted model, no parameter to tune at all — it estimates the baseline directly from local minima and maxima, automatically growing its own window size until the result stabilizes. No assumption about the background's shape (unlike ALS/airPLS/arPLS's smoothness penalty or I-ModPoly's polynomial), which makes it a reasonable option when a background is smooth but doesn't fit a fixed polynomial order or a single global penalty well. Being minimum-based, it tends to sit at or slightly below the true background rather than following it exactly — check the preview against the other methods if that matters for your data.</p>
            <p><b>mpls</b> is a genuine hybrid rather than a variant of either family above: it reuses Morphological Opening's own min/max machinery to pick out a handful of trustworthy "anchor" points, then solves ALS's own smoothness-penalty equation exactly once through them — no iterative reweighting loop at all, unlike every ALS/airPLS/arPLS-family method above. Worth trying when a spectrum's morphology already makes the baseline fairly obvious to the eye and you'd rather trust a small set of clearly-baseline points than tune a weighting rule iteration after iteration.</p>
            <p><b>Morphology + Mollification</b> takes the hybrid idea a step further than mpls: no system of equations to solve at all, not even a single one -- min/max operations and a fixed convolution kernel are both direct, explicit computations, nothing to solve for. Each pass takes the smaller of the raw spectrum and the average of a morphological closing/opening of the current baseline estimate, then smooths that with a fixed convolution kernel, repeating until the result stops changing. Like Morphological Opening, there's nothing to tune. Worth trying alongside Morphological Opening and mpls when a background's shape is already fairly clear from the spectrum itself.</p>
            <p><b>mpspline</b> is closest in spirit to mpls -- morphology picks out anchor points, then a single non-iterative fit runs through them, no reweighting loop -- but the fit itself is a compact cubic spline (a handful of smooth pieces joined together) rather than mpls's direct point-by-point Whittaker smoother, and it adds its own denoising pass first: a quick spline fit that trusts points a narrow morphological closing leaves untouched, before the anchor-finding step runs on that denoised curve instead of the raw spectrum. <b>Smoothness (λ)</b> and <b>Non-Anchor Weight (p)</b> work exactly as they do for mpls, just on λ's own separate scale (mpspline's penalty applies to the spline's own coefficients, not the data grid, so it isn't the same numeric scale as mpls's λ). Worth trying alongside mpls when the spectrum is large and a spline's smaller coefficient count is worth it, or simply as a second opinion built on genuinely different fitting machinery.</p>
            <p><b>jbcd</b> is the one hybrid here that doesn't reduce to "morphology picks anchor points, then one fit runs through them" at all -- it never singles out individual points as trustworthy. Instead it alternates between solving for a smooth, denoised version of the spectrum and a smooth baseline together, both pulled toward each other and toward the morphological opening (the same plain opening Morphological Opening computes), until neither changes further. <b>Baseline Fidelity to Opening (α)</b> sets how strongly the baseline is pulled toward that opening; <b>Baseline Smoothness Ceiling (β)</b> caps how strongly the baseline itself gets smoothed as the fit proceeds. Slower than every other method here since it solves a system twice per iteration rather than once, but worth trying when a spectrum is noisy enough that denoising and baseline-fitting genuinely benefit from being solved together rather than as two separate steps.</p>
        </div>

        <div class="tip">
            <strong>Apply vs. Add as New vs. Close:</strong>
            <ul>
                <li><b>Apply</b> replaces the spectra loaded in the dialog with their corrected result. The
                originals are overwritten once Apply runs.</li>
                <li><b>Add as New</b> leaves the originals completely untouched and adds the corrected
                result to the spectra list under new, unique names (e.g. <code>samplename_baseline_als</code>,
                <code>samplename_baseline_airpls</code>, <code>samplename_baseline_arpls</code>,
                <code>samplename_baseline_imodpoly</code>, or <code>samplename_baseline_morphological</code>
                depending on the method used, with a number appended if that name is already taken).</li>
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
        <h3>iarPLS</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role and the same numeric scale as arPLS's own λ slider (the dialog's iarPLS slider also defaults to <code>1e5</code>) — iarPLS reuses arPLS's second-difference penalty unchanged and only replaces the per-iteration weighting rule. iarPLS has no separate asymmetry parameter to tune.</li>
        </ul>
        <h3>asPLS</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role and the same numeric scale as ALS's own λ slider (the dialog's asPLS slider also defaults to <code>1e6</code>). No separate control for the adaptive point-by-point weighting — it's recomputed automatically from the residuals each iteration, not something to tune by hand. asPLS has no separate asymmetry parameter either.</li>
        </ul>
        <h3>drPLS</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role and the same numeric scale as arPLS's own λ slider (the dialog's drPLS slider also defaults to <code>1e5</code>) — this is the penalty applied to the overall curvature everywhere, before η relaxes it under peaks.</li>
            <li><b>Peak Relaxation (η):</b> A second slider unique to drPLS, on a 0–1 range (default <code>0.5</code>). It controls how much the smoothness penalty relaxes specifically in high-weight (peak) regions, independent of λ's setting for the rest of the spectrum — 0 behaves closest to arPLS's own fixed penalty everywhere, while values closer to 1 let peak regions deviate from the smooth background curve much more freely.</li>
        </ul>
        <h3>psalsa</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role and the same numeric scale as ALS's own λ slider (the dialog's psalsa slider also defaults to <code>1e6</code>) — psalsa reuses ALS's second-difference penalty unchanged and only replaces the weighting rule.</li>
            <li><b>Asymmetry (p):</b> Same role as ALS's p, but on its own 0.01–0.99 range (default <code>0.5</code>) rather than ALS's much smaller one — psalsa's exponential decay on peaks means p doesn't need to be as extreme as ALS's own <code>0.01</code> to keep peaks from dragging the fit up. The peak-height scale the decay runs on (k in the underlying formula) is set automatically from the spectrum's own noise level and isn't exposed as a separate slider.</li>
        </ul>
        <h3>I-ModPoly</h3>
        <ul>
            <li><b>Polynomial Order:</b> The degree of the single polynomial fitted to the whole spectrum (default <code>5</code>). Lower orders (e.g. <code>2</code>–<code>3</code>) follow only broad, simple curvature; higher orders can follow more background shape but risk fitting into broad peaks instead of around them — use the preview to check. I-ModPoly has no λ or asymmetry parameter at all; its iteration count and convergence threshold are fixed internally.</li>
        </ul>
        <h3>Morphological Opening</h3>
        <ul>
            <li><b>(no parameters)</b> Nothing to set. The structuring-element size every other method would need a slider for is instead grown automatically, starting from 3 points, until the result stops changing — see Technical Details below.</li>
        </ul>
        <h3>mpls</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role and the same numeric scale as ALS's own λ slider (the dialog's mpls slider also defaults to <code>1e6</code>) — mpls reuses ALS's second-difference penalty unchanged, just solved once instead of iteratively reweighted.</li>
            <li><b>Non-Anchor Weight (p):</b> A different quantity than ALS/psalsa's own p, on the same 0–1 range but defaulting to <code>0.00</code> rather than a small positive value. Morphology-identified "anchor" points always get weight <code>1 - p</code>; this slider sets the weight given to every other point, which is fully ignored (weight 0) by default. Raising it lets the rest of the spectrum start influencing the fit too, rather than only the anchor points.</li>
        </ul>
        <h3>Morphology + Mollification</h3>
        <ul>
            <li><b>(no parameters)</b> Nothing to set, same as Morphological Opening. The structuring-element window is grown automatically the same way, and the convergence tolerance / iteration cap for the min/max-plus-smoothing loop are fixed internally — see Technical Details below.</li>
        </ul>
        <h3>mpspline</h3>
        <ul>
            <li><b>Smoothness (λ):</b> Same role as mpls's own λ -- higher values give a stiffer, smoother baseline -- but on its own numeric scale, since it penalizes the fitted spline's coefficients rather than the data grid directly (the dialog's mpspline slider defaults to <code>1e4</code>, not mpls's <code>1e6</code>).</li>
            <li><b>Non-Anchor Weight (p):</b> Same role, same 0–1 range, and same <code>0.00</code> default as mpls's own p. Morphology-identified anchor points get weight <code>1 - p</code>; this slider sets the weight given to every other point, ignored entirely by default.</li>
        </ul>
        <h3>jbcd</h3>
        <ul>
            <li><b>Baseline Fidelity to Opening (α):</b> How strongly the fitted baseline is pulled toward the morphological opening, ranging 0.01–1.00 and defaulting to <code>0.10</code>. Not the same quantity as any other method's λ or p -- it weights one specific term in jbcd's own joint energy function (see Technical Details below).</li>
            <li><b>Baseline Smoothness Ceiling (β):</b> The ceiling jbcd's own internally-annealed smoothness weight is capped at, ranging 1.0–100.0 and defaulting to <code>10.0</code>. Unlike every λ slider above, this isn't the smoothness weight itself -- it only bounds how large that weight is allowed to grow as the fit iterates (see Technical Details below for why the cap is needed at all).</li>
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
        <h3>iarPLS</h3>
        <p>iarPLS keeps arPLS's second-difference penalized-least-squares fit unchanged and only replaces the weighting rule, to fix arPLS's documented tendency to overestimate the baseline under small peaks in noisy data. The threshold is built from only the standard deviation <code>s</code> of the negative residuals (no mean term), and the weighting curve itself sharpens as iterations proceed: at iteration <code>i</code>, <code>w = 0.5 (1 - g / sqrt(1 + g²))</code> where <code>g = (exp(min(i, 100)) / s)·(d - 2s)</code>. That <code>x / sqrt(1 + x²)</code> curve (an ISRU-style function) is self-normalizing and can never overflow the way arPLS's raw <code>exp()</code> weighting needed explicit clipping for, while the <code>exp(min(i, 100))</code> term makes the cutoff between "baseline" and "peak" progressively sharper in later iterations. Iteration stops once the weight vector stops changing appreciably between steps, or after a fixed number of iterations.</p>
        <h3>asPLS</h3>
        <p>asPLS is the one method here where the smoothness penalty itself isn't a single scalar λ applied uniformly. Each iteration solves <code>(W + diag(α)·λ DᵀD) z = W y</code> — the same second-difference <code>D</code> as ALS/arPLS, but scaled point-by-point by an adaptive diagonal <code>α</code> rather than a flat <code>λ</code>. <code>α</code> starts at 1 everywhere (a plain solve on the first pass) and is then recomputed after every iteration as <code>αᵢ = |residualᵢ| / max(|residual|)</code>: points near the current fit (confidently baseline) pull toward <code>α ≈ 0</code>, loosening the penalty there, while points with a large residual keep <code>α</code> close to 1 and stay stiffly smoothed. Weights use a simpler logistic curve than arPLS's, thresholded at just the negative residuals' own standard deviation <code>s</code> (no mean term): <code>w = 1 / (1 + exp(k(d - s)/s))</code>, with the steepness <code>k</code> fixed internally at <code>0.5</code> — not the reference paper's own value of 2, which the open-source implementations this was checked against found fits noisy data closer to the paper's own reported results than 2 does. Iteration stops once the weight vector stops changing appreciably between steps, or after a fixed number of iterations.</p>
        <h3>drPLS</h3>
        <p>drPLS solves a different linear system each iteration than the other arPLS-family methods here, one that can't be reduced to a single λ·DᵀD penalty. Alongside the usual second-difference penalty matrix <code>Pₙ = λ D2ᵀD2</code>, it adds an unweighted first-difference penalty <code>P₁ = D1ᵀD1</code> (discouraging an overall sloped baseline, not just curvature) and solves <code>(P₁ + Pₙ + W − η·W·Pₙ) z = W y</code> — the <code>−η·W·Pₙ</code> cross term is what relaxes the second-difference penalty specifically where the weights <code>W</code> are large, i.e. under points the fit currently treats as peaks. Weighting reuses arPLS's own threshold (the negative residuals' mean and standard deviation) but through a softsign curve sharpened by an iteration-dependent factor, the same sharpening iarPLS uses: <code>w = 0.5·(1 − inner / (1 + |inner|))</code>, where <code>inner</code> grows with each iteration and pushes weights toward their extremes as the fit converges. Iteration stops once the weight vector stops changing appreciably between steps, or after a fixed number of iterations.</p>
        <h3>psalsa</h3>
        <p>psalsa fits the same penalized-least-squares equation as ALS (second-difference smoothness penalty), but replaces ALS's hard p / (1 - p) split with an exponential decay above the fit: for a residual <code>d = y - z</code>, points at or below the fit (<code>d ≤ 0</code>) get the fixed weight <code>1 - p</code>, same as ALS, while points above it (<code>d &gt; 0</code>) get <code>w = p·exp(-d / k)</code>, where <code>k</code> sets the residual scale the decay runs on (roughly "how tall counts as a peak") and defaults to one-tenth of the spectrum's own standard deviation. A small bump just above the fit keeps close to its full <code>p</code> weight, while a tall peak's weight collapses toward 0 almost immediately — which is what lets p be set much higher here than ALS typically needs while still suppressing real peaks. Iteration stops once the weight vector stops changing appreciably between steps, or after a fixed number of iterations.</p>
        <h3>I-ModPoly</h3>
        <p>I-ModPoly fits a single polynomial of the chosen order by least squares, then rebuilds the working spectrum for the next fit: points within one residual standard deviation of the current fit keep their own value, points further above it are pulled down to the fit itself, so real peaks stop dragging the polynomial upward. The very first iteration also permanently drops any point more than one residual standard deviation above that initial fit, before the per-iteration reconstruction rule starts running on what's left. Iteration stops once the residual standard deviation changes by less than 5% (relative) between iterations — an automated cutoff built into the method itself — or after a fixed number of iterations.</p>
        <h3>Morphological Opening</h3>
        <p>Erosion replaces each point with the minimum value in a window of width <code>Y</code> centered on it; dilation replaces each point with the maximum. Opening is erosion followed by dilation with the same window — a min-then-max pass that tracks the spectrum's lower envelope without following sharp, narrow peaks up. Starting from a 3-point window, the window is grown by 2 points and the opening recomputed each time; once three consecutive openings come out exactly identical, growth stops, and the smallest of those three window sizes is the "optimal" one — no window size to choose by hand. That opening is then refined once more to correct for band-shape distortion it can introduce: it's dilated and eroded again with the same optimal window, the two results averaged, and the final baseline is whichever is lower at each point — the averaged correction or the plain opening — so the correction only ever pulls the curve down, never up.</p>
        <h3>mpls</h3>
        <p>mpls runs the same window-growth procedure as Morphological Opening to get a rough opening of the spectrum, but uses it only to locate "anchor points" rather than as the baseline itself: a point is a boundary of one of the opening's flat runs if exactly one of its two neighboring differences is zero, and the minimum y-value within each pair of consecutive boundaries becomes that run's anchor. Anchor points get weight <code>1 - p</code>, every other point gets weight <code>p</code>, and ALS's own equation, <code>(W + λ DᵀD) z = W y</code>, is solved exactly once with those weights — no iterative reweighting loop at all, unlike every ALS/airPLS/arPLS-family method above. (When the opening has no internal flat-region boundaries at all — e.g. a perfectly flat or perfectly monotonic spectrum — every point is treated as an anchor instead, since nothing in the morphology singles any point out as more "baseline" than any other.)</p>
        <h3>Morphology + Mollification</h3>
        <p>The only method here with no system of equations to solve at all, Whittaker or otherwise -- min/max operations and convolution with a fixed kernel are both direct, explicit computations rather than something solved for. Using the same auto-grown window as Morphological Opening, each pass takes the element-wise minimum of the original spectrum against the average of a morphological closing and opening of the <em>current</em> baseline estimate — the "averaging" step that keeps the estimate from drifting up into real peaks over repeated passes — then smooths that candidate by convolving it with a fixed "mollifier" kernel: a standard, infinitely smooth, compactly-supported bump function from real analysis (<code>exp(-1 / (1 - x²))</code> over its own local coordinate x in (-1, 1), zero beyond it, normalized to sum to 1), not something invented for this algorithm. The spectrum is padded on both ends first (linear extrapolation from each edge's own local trend) so the repeated convolutions don't distort the two ends. Iteration stops once the baseline stops changing appreciably between passes, or after a fixed number of iterations.</p>
        <h3>mpspline</h3>
        <p>mpspline fits a cubic penalized spline -- a fixed set of smooth polynomial pieces joined at evenly-spaced "knots", regularized by a penalty on how much the pieces' own coefficients change from one to the next -- rather than the direct point-by-point penalty every Whittaker-family method above uses. That needs far fewer effective degrees of freedom than a Whittaker fit, one of this method's original selling points for large spectra. Two non-iterative spline fits run in sequence: first a lightly-regularized "denoising" fit, trusting only points a narrow (3-point) morphological closing leaves untouched, producing a cleaned-up curve; then the same window-growth procedure Morphological Opening and mpls both use runs on <em>that</em> curve instead of the raw spectrum, to locate anchor points the same way mpls does (morphological opening corrected toward the average of its own erosion and dilation, points where the denoised curve matches that corrected curve exactly become anchors). A second spline, at the user-facing <b>Smoothness (λ)</b>, is then fit through those anchor points weighted <code>1 - p</code> (every other point weighted <code>p</code>) -- this second fit is the returned baseline. (When no anchors are found at all -- a perfectly flat or monotonic curve -- every point is treated as an anchor instead, the same fallback mpls uses for the same edge case.)</p>
        <p>The number of knots the spline is built from is not exposed as a slider -- it's set internally, scaled to half the number of fitted points (capped for performance on very large spectra) rather than a single fixed count regardless of spectrum size. A fixed small knot count, the literal default in both the original paper and the open-source implementation this was checked against, ties the two spline pieces on either side of a knot together loosely enough that a tall, narrow peak -- common in real Raman spectra -- can make the first (denoising) fit ring well beyond the peak's own width before the second fit has a chance to correct it, visibly overestimating the baseline nearby; scaling the knot count with the spectrum keeps each pair of neighboring knots close enough together that this doesn't happen, confirmed against synthetic spectra with peaks only a few samples wide.</p>
        <h3>jbcd</h3>
        <p>jbcd solves a single joint energy function for a smooth, denoised spectrum <code>f</code> and a smooth baseline <code>b</code> together: <code>E(f,b) = ½‖f+b-g‖² + α‖b-Og‖² + β<sub>t</sub>‖D₁b‖² + γ<sub>t</sub>‖D₁f‖²</code>, where <code>g</code> is the raw spectrum, <code>Og</code> is the plain morphological opening of <code>g</code> (the same auto-grown-window opening Morphological Opening computes, but without that method's own erosion/dilation-averaged refinement step), and <code>D₁</code> is the first-difference operator, so <code>‖D₁x‖²</code> penalizes <code>x</code>'s own slope rather than curvature the way every Whittaker-family method's second-difference penalty does. The first term keeps <code>f+b</code> a faithful reconstruction of <code>g</code>; the second pulls <code>b</code> toward the morphological guide <code>Og</code> at the user-facing weight <code>α</code>, fixed throughout; the third and fourth smooth <code>b</code> and <code>f</code> respectively, at their own weights <code>β<sub>t</sub></code> and <code>γ<sub>t</sub></code>, which change every iteration rather than staying fixed. It's solved by alternating minimization: fix <code>b</code>, solve for <code>f</code>; fix that <code>f</code>, solve for <code>b</code>; repeat until both stop changing appreciably. Each half-step reduces to the same kind of weighted linear system every Whittaker-family method above already solves exactly, just with <code>D₁</code> in place of the usual second-difference operator.</p>
        <p><code>β<sub>t</sub></code> and <code>γ<sub>t</sub></code> anneal every iteration -- <code>β<sub>t</sub></code> grows, <code>γ<sub>t</sub></code> shrinks -- shifting weight from denoising toward fidelity as the fit settles, starting from internal-only initial values. Run for long enough, unbounded growth in <code>β<sub>t</sub></code> eventually swamps the fidelity term in the baseline step's own linear system to the point of numerical breakdown, collapsing the baseline to a near-constant flat line regardless of <code>α</code> -- not something the reference's own reported examples ran long enough to hit, but reachable on some spectra here. <b>Baseline Smoothness Ceiling (β)</b> caps <code>β<sub>t</sub></code>'s growth at a user-facing ceiling to prevent this. <code>γ<sub>t</sub></code>'s own initial value, and both parameters' fixed annealing ratios, were found to only change how many iterations convergence takes, not the converged baseline itself -- so unlike the reference's own three regularization weights, only two (<code>α</code> and the <code>β</code> ceiling) are exposed here.</p>

        <h2>References</h2>
        <ul>
            <li>Eilers, P. H. C., & Boelens, H. F. M. (2005). <i>Baseline Correction with Asymmetric Least Squares Smoothing</i>. Leiden University Medical Centre Report. (ALS)</li>
            <li>Zhang, Z.-M., Chen, S., & Liang, Y.-Z. (2010). <i>Baseline correction using adaptive iteratively reweighted penalized least squares.</i> Analyst, 135(5), 1138–1146. (airPLS)</li>
            <li>Baek, S.-J., Park, A., Ahn, Y.-J., & Choo, J. (2015). <i>Baseline correction using asymmetrically reweighted penalized least squares smoothing.</i> Analyst, 140(1), 250–257. (arPLS)</li>
            <li>Ye, J., Tian, Z., Wei, H., & Li, Y. (2020). <i>Baseline correction method based on improved asymmetrically reweighted penalized least squares for the Raman spectrum.</i> Applied Optics, 59(34), 10933–10943. (iarPLS)</li>
            <li>Zhang, F., Tang, X., Tong, A., Wang, B., Wang, J., Lv, Y., Tang, C., & Wang, J. (2020). <i>Baseline correction for infrared spectra using adaptive smoothness parameter penalized least squares method.</i> Spectroscopy Letters, 53(3), 222–233. (asPLS)</li>
            <li>Xu, D., Liu, S., Cai, Y., & Yang, C. (2019). <i>Baseline correction method based on doubly reweighted penalized least squares.</i> Applied Optics, 58(14), 3913–3920. (drPLS)</li>
            <li>Oller-Moreno, S., Pardo, A., Jimenez-Soto, J. M., Samitier, J., & Marco, S. (2014). <i>Adaptive Asymmetric Least Squares baseline estimation for analytical instruments.</i> 2014 IEEE 11th International Multi-Conference on Systems, Signals & Devices (SSD14), 1–5. (psalsa)</li>
            <li>Lieber, C. A., & Mahadevan-Jansen, A. (2003). <i>Automated method for subtraction of fluorescence from biological Raman spectra.</i> Applied Spectroscopy, 57(11), 1363–1367. (base polynomial method underlying I-ModPoly)</li>
            <li>Zhao, J., Lui, H., McLean, D. I., & Zeng, H. (2007). <i>Automated autofluorescence background subtraction algorithm for biomedical Raman spectroscopy.</i> Applied Spectroscopy, 61(11), 1225–1232. (I-ModPoly)</li>
            <li>Perez-Pueyo, R., Soneira, M. J., & Ruiz-Moreno, S. (2010). <i>Morphology-based automated baseline removal for Raman spectra of artistic pigments.</i> Applied Spectroscopy, 64(6), 595–600. (Morphological Opening)</li>
            <li>Li, Z., Zhan, D., Wang, J., Huang, J., Xu, Q., Zhang, Z., Zheng, Y., Liang, Y., & Wang, H. (2013). <i>Morphological weighted penalized least squares for background correction.</i> Analyst, 138(16), 4483–4492. (mpls)</li>
            <li>Koch, M., Suhr, C., Roth, B., & Meinhardt-Wollweber, M. (2017). <i>Iterative morphological and mollifier-based baseline correction for Raman spectra.</i> Journal of Raman Spectroscopy, 48(2), 336–342. (Morphology + Mollification — introduces the mollifier-kernel approach)</li>
            <li>Chen, H., Xu, W., & Broderick, N. G. R. (2019). <i>An adaptive and fully automated baseline correction method for Raman spectroscopy based on morphological operations and mollification.</i> Applied Spectroscopy, 73(3), 284–293. (Morphology + Mollification — adds the closing/opening "averaging" refinement used here)</li>
            <li>Gonzalez-Vidal, J. J., Perez-Pueyo, R., & Soneira, M. J. (2017). <i>Automatic morphology-based cubic p-spline fitting methodology for smoothing and baseline-removal of Raman spectra.</i> Journal of Raman Spectroscopy, 48(6), 878–883. (mpspline — the two-stage morphology + cubic p-spline method itself)</li>
            <li>Liu, H., Zhang, Z., Liu, S., Yan, L., Liu, T., & Zhang, T. (2015). <i>Joint Baseline-Correction and Denoising for Raman Spectra.</i> Applied Spectroscopy, 69(9), 1013–1022. (jbcd)</li>
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