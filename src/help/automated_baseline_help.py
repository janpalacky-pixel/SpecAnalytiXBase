# src/help/automated_baseline_help.py

def get_automated_baseline_help_title():
    """Return the title for automated baseline correction help."""
    return "Automated Baseline Correction (ALS) Help"

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
        <p>This tool uses the <b>Asymmetric Least Squares (ALS)</b> algorithm to automatically detect and remove curving baselines. It is enhanced with <b>region-specific fitting</b>, allowing you to define which parts of the spectrum the algorithm should use for its calculation.</p>
        
        <h2>Workflow</h2>
        <ol>
            <li>Select a spectrum from the list on the left to preview it.</li>
            <li>Define the regions for the baseline calculation using one of the two modes below.</li>
            <li>Adjust the <b>Smoothness (λ)</b> and <b>Asymmetry (p)</b> sliders to fine-tune the fit.</li>
            <li>Observe the real-time preview to ensure the baseline is correct.</li>
            <li>Click <b>Apply</b> to replace the selected spectra with the corrected result, or
                <b>Add as New</b> to keep the originals untouched and add the result under new names.</li>
        </ol>

        <div class="tip">
            <strong>Apply vs. Add as New vs. Close:</strong>
            <ul>
                <li><b>Apply</b> replaces the spectra loaded in the dialog with their corrected result. The
                originals are overwritten once Apply runs.</li>
                <li><b>Add as New</b> leaves the originals completely untouched and adds the corrected
                result to the spectra list under new, unique names (e.g. <code>samplename_baseline_als</code>,
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
        </div>

        <h2>Parameters Explained</h2>
        <ul>
            <li><b>Smoothness (λ):</b> Controls how stiff or flexible the baseline is. Higher values (e.g., <code>1e7</code>) create a very smooth line for broad backgrounds. Lower values (e.g., <code>1e4</code>) create a more flexible line that can follow local variations.</li>
            <li><b>Asymmetry (p):</b> Controls how much the algorithm penalizes peaks. A value of <code>0.01</code> is a good start. Lower values are for sharp peaks; higher values can be used for broader peaks or noisy data.</li>
        </ul>

        <h2>Technical Details</h2>
        <p>The ALS algorithm iteratively finds a baseline (<code>z</code>) that minimizes the following equation:</p>
        <code>Σw(y - z)² + λΣ(Δ²z)²</code>
        <ul>
            <li>The first term <code>Σw(y - z)²</code> is the "fidelity" term. It tries to keep the baseline <code>z</code> close to the original signal <code>y</code>. The weights <code>w</code> are adjusted at each step based on the asymmetry parameter <code>p</code>, which heavily penalizes points where the signal is above the baseline (i.e., peaks).</li>
            <li>The second term <code>λΣ(Δ²z)²</code> is the "smoothness" penalty. It penalizes curvature in the baseline. The smoothness parameter <code>λ</code> controls how much influence this term has.</li>
        </ul>

        <h2>References</h2>
        <p>The algorithm implemented here is based on the work by Eilers & Boelens:</p>
        <ul>
            <li>Eilers, P. H. C., & Boelens, H. F. M. (2005). <i>Baseline Correction with Asymmetric Least Squares Smoothing</i>. Leiden University Medical Centre Report.</li>
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