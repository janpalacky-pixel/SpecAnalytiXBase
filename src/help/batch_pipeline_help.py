# src/help/batch_pipeline_help.py


def get_batch_pipeline_help_title():
    return 'Batch Pipeline Replay — help'


def get_batch_pipeline_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            .cat    { background: #f5f5f5; padding: 10px 14px; margin: 6px 0; border-radius: 5px; }
            .tip    { background: #E8F5E9; border-left: 4px solid #2E7D32;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .note   { background: #E3F2FD; border-left: 4px solid #1565C0;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .warn   { background: #FFF8E1; border-left: 4px solid #F9A825;
                      padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm     { font-family: monospace; background: #ececec;
                      padding: 1px 5px; border-radius: 3px; }
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

    <h1>Batch Pipeline Replay</h1>

    <p>A <strong>pipeline</strong> is a named, ordered sequence of processing
    operations (baseline correction, normalization, smoothing, etc.) with
    their exact settings — captured once from a session's Operations
    History, then reusable on any spectra selection, in this session or a
    future one, with a single click. It's the difference between manually
    repeating a 4-step recipe on every new batch of spectra you import, and
    running "Raman standard prep" once.</p>

    <hr>
    <h2 id="save">Saving a pipeline</h2>
    <ol>
        <li>Process a spectrum (or spectra) the normal way — Baseline
            correction, Normalization, SG Smoothing, whatever sequence you
            want to capture — each step applied with Apply as usual.</li>
        <li>Open <strong>Operations History</strong> and click
            <strong>Save as Pipeline...</strong></li>
        <li>Every operation committed so far this session is listed, in
            order, with a checkbox. Eligible steps are checked by default;
            steps that can't be captured into a pipeline are shown greyed
            out with a tooltip explaining why (see
            <a href="#eligibility">Which operations can be included</a>
            below).</li>
        <li>Uncheck anything you don't want included, give the pipeline a
            name, and click <strong>Save</strong>. It's now stored
            permanently — closing the app and starting a new session does
            not lose it.</li>
    </ol>

    <hr>
    <h2 id="run">Running a pipeline</h2>
    <ol>
        <li>Select the spectra you want to process in the main spectrum
            list — exactly as you would before opening any other operation
            dialog.</li>
        <li>Open <strong>Operations → Batch Pipeline → Run Pipeline...</strong></li>
        <li>Pick a saved pipeline from the dropdown. Its steps are shown, in
            order, below.</li>
        <li><strong>Apply</strong> replaces the selected spectra with the
            pipeline's output; <strong>Add as New</strong> keeps the
            originals and adds the output as new spectra
            (<span class="fm">_pipeline_&lt;name&gt;</span> suffix).</li>
    </ol>

    <div class="note">
        Each step is validated before it runs (enough spectra selected,
        common x-axis where required). If a step's precondition isn't met,
        the whole run stops there and reports exactly which step and why —
        nothing already-applied silently continues past a failure.
    </div>

    <hr>
    <h2 id="eligibility">Which operations can be included</h2>

    <p>A pipeline step needs a settings dict that applies identically,
    correctly, to whatever spectra it's later run on. That's true for most
    single-spectrum transforms, but not all of them:</p>

    <table>
        <colgroup>
            <col style="width:27%;">
            <col style="width:73%;">
        </colgroup>
        <tr><th>Included</th><th>Excluded, and why</th></tr>
        <tr>
            <td>
                <ul style="margin:0; padding-left:16px;">
                    <li>SNIP Baseline</li>
                    <li>Automated Baseline (ALS / airPLS / arPLS / iarPLS / asPLS / psalsa / I-ModPoly / Morphological)</li>
                    <li>Normalization<sup>*</sup></li>
                    <li>SG Smoothing</li>
                    <li>FFT Denoising</li>
                    <li>Cosmic Ray Removal</li>
                    <li>Spike Removal</li>
                    <li>Resolution Enhancement</li>
                    <li>X-axis Unit Conversion</li>
                    <li>Data Range / linearization<sup>†</sup></li>
                </ul>
            </td>
            <td>
                <p style="margin:0 0 10px 0;"><strong>Manual baseline</strong> — stateful:
                points are placed by hand on one specific spectrum's curve; a new
                target has no matching points.</p>
                <p style="margin:0 0 10px 0;"><strong>CD Unit Conversion</strong> — settings
                (concentration, path length, molecular weight) are tied to one
                specific sample; replaying them on a different spectrum would
                silently apply the wrong sample's physical parameters.</p>
                <p style="margin:0 0 10px 0;"><strong>SVD Background, SVD Interpolation,
                Interactive Subtraction, Combine Spectra, Spectral Calculator</strong> —
                each works across a specific chosen set of OTHER spectra (a basis,
                a reference set, named formula inputs), not a settings dict that
                applies to each spectrum independently.</p>
                <p style="margin:0;"><strong>X-axis alignment</strong> — aligns to
                one reference spectrum from the original selection, which may not
                exist (or not be the right one) in a different selection.</p>
            </td>
        </tr>
    </table>

    <p><sup>*</sup> <strong>Normalization caveat:</strong> Reference mode
    designates the reference spectrum by its <em>position</em> in the
    selection, not by name. Replaying this step on a different or
    reordered selection uses whichever spectrum happens to sit at that
    position then, which may not be the one you intended — the Run Pipeline
    dialog flags this with a warning for any such step. Every other
    Normalization mode has no such caveat.</p>

    <p><sup>†</sup> <strong>Data Range caveat:</strong> only the batch-shared
    settings (ranges, include/exclude mode, linearization step) are
    replayed. Any per-spectrum range override recorded for the original
    spectra is not — those were tied to the specific spectra they were
    entered for.</p>

    <hr>
    <h2 id="caveats">Other things to know</h2>
    <div class="warn">
    <ul>
        <li><strong>No branching / versioning.</strong> Saving under an
            existing pipeline's name overwrites it — there's no history of
            previous versions of a pipeline, only of the operations you
            originally ran to build it (still visible in that session's
            Operations History).</li>
        <li><strong>A pipeline step's settings are frozen at save time.</strong>
            Editing a saved pipeline isn't currently supported — delete it
            and save a new one under the same name if you need to change a
            step.</li>
        <li><strong>Order matters.</strong> Steps always run in the order
            shown, top to bottom; each step's output becomes the next
            step's input.</li>
    </ul>
    </div>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
