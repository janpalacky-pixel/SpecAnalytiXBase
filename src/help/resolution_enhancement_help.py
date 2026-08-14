# src/help/resolution_enhancement_help.py

def get_resolution_help_title():
    return 'Spectral Resolution Enhancement — Help'

def get_resolution_help_content():
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

    <h1>Spectral Resolution Enhancement (Wiener deconvolution)</h1>

    <p>Every spectrometer broadens spectral features by an amount determined
    by its <strong>instrument response function (IRF)</strong> — the spread
    function of the optics, CCD, and entrance slit. Wiener deconvolution
    mathematically reverses this broadening to recover sharper spectral features.</p>

    <div class="note">
        <strong>What it does:</strong> overlapping bands become more separated,
        peak positions become more accurate, and the apparent resolution
        increases. It does <em>not</em> create information that was not in the
        original measurement — it recovers information that was blurred by
        the instrument.
    </div>

    <hr>
    <h2>Algorithm</h2>
    <p>The measured spectrum y<sub>m</sub> is modelled as the convolution of
    the true spectrum y<sub>t</sub> with the IRF h:</p>
    <p style="margin-left:16px"><span class="fm">y_m = y_t * h</span></p>
    <p>Wiener deconvolution recovers y<sub>t</sub> in Fourier space:</p>
    <p style="margin-left:16px">
        <span class="fm">Y_t(f) = Y_m(f) &times; H*(f) / (|H(f)|&sup2; + 1/SNR)</span>
    </p>
    <p>The IRF is modelled as a <strong>Gaussian</strong> with half-width
    &sigma; (in x-axis units). The <strong>SNR</strong> parameter controls
    regularisation — it prevents noise amplification at the cost of
    less aggressive sharpening.</p>

    <hr>
    <h2>Parameters</h2>
    <table>
        <tr><th>Parameter</th><th>Description</th></tr>
        <tr><td><strong>IRF width (&sigma;)</strong></td>
            <td>Gaussian half-width of the instrument response in x-axis units.
                Typical values:
                <ul>
                    <li>High-resolution Raman: 0.5&ndash;2&nbsp;cm&sup1;</li>
                    <li>Standard Raman: 2&ndash;5&nbsp;cm&sup1;</li>
                    <li>Low-resolution / FTIR: 4&ndash;16&nbsp;cm&sup1;</li>
                </ul>
                Use <em>Estimate &sigma; from peak width&hellip;</em> to
                compute &sigma; from a measured FWHM:
                &sigma; = FWHM / 2.355
            </td></tr>
        <tr><td><strong>SNR</strong></td>
            <td>Signal-to-noise ratio of your spectra. Controls the
                trade-off between sharpening and noise amplification.<br>
                <ul>
                    <li>Clean spectra (low noise): 500&ndash;1000</li>
                    <li>Typical spectra: 50&ndash;200</li>
                    <li>Noisy spectra: 10&ndash;50</li>
                </ul>
                Start at 100 and increase until artefacts appear in the
                preview, then reduce slightly.
            </td></tr>
    </table>

    <hr>
    <h2>Estimating the IRF width</h2>
    <p>The best way to measure the IRF is to measure a sample with a known
    very sharp spectral line and measure its FWHM in your instrument:</p>
    <ul>
        <li><strong>Raman:</strong> silicon reference at 520.7&nbsp;cm&sup1;</li>
        <li><strong>Raman:</strong> neon or argon lamp emission lines</li>
        <li><strong>IR/FTIR:</strong> polystyrene reference card</li>
    </ul>
    <p>Measure the FWHM of the reference peak (in cm&sup1; or nm), then
    click <em>Estimate &sigma; from peak width&hellip;</em> and enter the FWHM.
    The dialog will compute &sigma; = FWHM / 2.355 automatically.</p>

    <div class="tip">
        <strong>Rule of thumb:</strong> if you do not know the IRF width,
        start with &sigma; = 2&ndash;3&nbsp;cm&sup1; for Raman and watch
        the preview. Increase &sigma; if bands are still too broad;
        decrease if artefacts (ringing, negative dips) appear.
    </div>

    <hr>
    <h2>Residual view</h2>
    <p>Tick <em>Show residual (original &minus; enhanced)</em> to overlay
    the difference between the original and enhanced spectrum. A flat residual
    near zero indicates the enhancement was conservative. A structured residual
    shows which features were sharpened.</p>

    <hr>
    <h2>Limitations and warnings</h2>
    <div class="warn">
        <strong>Ringing artefacts:</strong> aggressive deconvolution (high SNR,
        large &sigma;) causes Gibbs ringing — oscillations around sharp peaks.
        Reduce SNR or &sigma; if the preview shows dips adjacent to peaks.
    </div>
    <div class="warn">
        <strong>Noise amplification:</strong> deconvolution amplifies high-frequency
        noise. Apply smoothing (Savitzky-Golay) before enhancement if spectra
        are noisy. The SNR parameter controls this trade-off.
    </div>
    <div class="warn">
        <strong>Not a substitute for a better instrument.</strong>
        Deconvolution cannot recover information that was lost to noise. It
        works best on clean, high-SNR spectra from instruments where broadening
        (not noise) is the main limitation.
    </div>

    <hr>
    <h2>Recommended workflow</h2>
    <ol>
        <li>Remove cosmic rays and apply baseline correction first.</li>
        <li>If spectra are noisy, apply light Savitzky-Golay smoothing.</li>
        <li>Estimate &sigma; from a reference peak or use a typical value for
            your instrument.</li>
        <li>Start with SNR = 100. Increase until ringing appears; use the
            value just below.</li>
        <li>Check the preview for all representative spectrum types before
            committing.</li>
        <li>Click <strong>Apply</strong> to replace the selected spectra with the enhanced
            result, or <strong>Add as New</strong> to keep the originals and add the result
            under new names.</li>
    </ol>

    <hr>
    <h2>Committing the result</h2>
    <ul>
        <li><strong>Apply</strong> replaces the spectra loaded in the dialog with their
            resolution-enhanced result. The originals are overwritten once Apply runs.</li>
        <li><strong>Add as New</strong> leaves the originals completely untouched and adds
            the enhanced result to the spectra list under new, unique names (e.g.
            <span class="fm">samplename_enhanced</span>, with a number appended if that name
            is already taken).</li>
        <li><strong>Close</strong> closes the dialog without applying anything to the main
            window's spectra. Whatever settings were last shown are still remembered the next
            time you reopen it for the same spectra.</li>
    </ul>
    <p>There is no separate Run step in the main window for this operation — Apply and Add
    as New commit immediately, after which the dialog closes automatically.</p>

    <div class="note">
        <strong>If a spectrum can't be enhanced</strong> (too few points, or a degenerate
        result), it's left completely unchanged rather than corrupted or aborting the whole
        batch — Apply/Add as New will tell you which spectrum, if any, this happened to.
    </div>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    this dialog's own spectrum list.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    <hr>
    <h2 id="references">References</h2>
    <p style="font-size: 12px;">
    Wiener, N. (1949). <em>Extrapolation, Interpolation, and Smoothing of
    Stationary Time Series</em>. MIT Press, Cambridge, MA. (Original
    Wiener filter/deconvolution theory this tool's Fourier-space
    deconvolution implements.)
    </p>

    </body></html>
    """
