# src/help/fft_denoising_help.py


def get_fft_denoising_help_title():
    return 'FFT Denoising — help'


def get_fft_denoising_help_content():
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

    <h1>FFT Denoising</h1>

    <p>FFT Denoising filters spectra in the <em>frequency domain</em> by
    selectively zeroing frequency components that correspond to unwanted signal
    contributions — most commonly slow baseline drift (very low frequencies) and
    high-frequency electronic or shot noise.</p>

    <p>Because Raman and IR band shapes are intermediate-frequency features,
    a well-chosen filter leaves the peaks intact while removing artefacts that
    live at the extreme ends of the frequency spectrum.</p>

    <div class="note">
        <strong>Typical pipeline position:</strong><br>
        Data range &rarr; <strong>FFT Denoising</strong> &rarr; Baseline correction
        &rarr; Normalization &rarr; further analysis.<br>
        Run before baseline correction so that the baseline fitter works on a
        smoother signal. Alternatively run after baseline correction to further
        reduce residual noise before peak fitting.
    </div>

    <hr>
    <h2>Workflow</h2>
    <ol>
        <li><strong>Select spectra</strong> in the main window.</li>
        <li><strong>Open Parameters</strong> to open the FFT Denoising dialog.</li>
        <li><strong>Inspect the Power spectrum tab</strong> — the single-sided
            amplitude spectrum shows where signal energy is concentrated. Baseline
            drift appears as elevated amplitude near frequency&nbsp;0; electronic
            noise spreads energy across the high-frequency end.</li>
        <li><strong>Use Quick cut</strong> — set a percentage and click
            <strong>Cut low</strong> and/or <strong>Cut high</strong> — while watching
            the <em>Signal preview</em> or <em>Power&nbsp;+&nbsp;Signal</em> tabs
            update live. Each click adds a band to the same stop-bands table below,
            so everything being removed shows up in one place.</li>
        <li>Optionally add more specific <strong>stop-bands</strong> by hand (F low /
            F high + Add band) to target a narrow noise spike visible in the power
            spectrum.</li>
        <li>Click <strong>Apply</strong> to replace the selected spectra with the denoised
            result, or <strong>Add as New</strong> to keep the originals and add the result
            under new names.</li>
    </ol>

    <div class="tip">
        <strong>Apply vs. Add as New vs. Close:</strong>
        <ul>
            <li><strong>Apply</strong> replaces the spectra loaded in the dialog with their
            denoised result. The originals are overwritten once Apply runs.</li>
            <li><strong>Add as New</strong> leaves the originals completely untouched and
            adds the denoised result to the spectra list under new, unique names (e.g.
            <span class="fm">samplename_denoised</span>, with a number appended if that name
            is already taken).</li>
            <li><strong>Close</strong> closes the dialog without applying anything to the
            main window's spectra. Whatever settings were last shown are still remembered
            the next time you reopen it for the same spectra.</li>
        </ul>
        <p>There is no separate Run step in the main window for this operation — Apply and
        Add as New commit immediately, after which the dialog closes automatically.</p>
    </div>

    <div class="note">
        <strong>If a spectrum can't be denoised</strong> (an unexpected numerical issue),
        it's left completely unchanged rather than dropped from the result or corrupted —
        Apply/Add as New will tell you which spectrum, if any, this happened to.
    </div>

    <div class="tip">
        Use the <strong>Power + Signal</strong> tab to tune the filter and see both
        the frequency-domain effect and the reconstructed signal side-by-side without
        switching tabs. Switch to <strong>All spectra&nbsp;— denoised</strong> to
        verify the filter is consistent across the whole dataset.
    </div>

    <hr>
    <h2 id="filters">Filter reference</h2>

    <p>Everything that gets removed — whether a whole low/high end of the
    spectrum or one narrow spike — lives in a single <strong>stop-bands
    table</strong>. There's no separate parallel mechanism for the common
    low/high case; <strong>Quick cut</strong> just adds a band to that same
    table for you.</p>

    <table>
        <tr><th>Control</th><th>Effect</th><th>Typical value</th></tr>
        <tr>
            <td><strong>Quick cut &mdash; Cut low</strong></td>
            <td>Adds a stop-band from 0 up to the percentage entered next to
                the button — zeros all frequencies <em>below</em> it
                (removes DC and sub-baseline variation).</td>
            <td>0.5&ndash;5&nbsp;% for Raman spectra with smooth baseline drift.</td>
        </tr>
        <tr>
            <td><strong>Quick cut &mdash; Cut high</strong></td>
            <td>Adds a stop-band from the percentage entered next to the
                button up to Nyquist — zeros all frequencies
                <em>above</em> it (removes HF electronic / shot noise).</td>
            <td>30&ndash;60&nbsp;%; lower values give heavier smoothing
                but may broaden peaks.</td>
        </tr>
        <tr>
            <td><strong>Stop-bands table</strong></td>
            <td>Zeros a specific [f_lo, f_hi] interval.
                Multiple bands can be stacked — Quick cut bands and manually
                typed bands all sit in the same list.
                Values are in the normalised 0–1 scale
                (not %). Set F low/F high above the table and click
                <strong>Add band</strong>; click a row in the table to select
                it — the button relabels itself <strong>Update band</strong>
                (with a <strong>Cancel edit</strong> button right next to it) so
                you can change that band's values in place instead of adding a
                duplicate. Adding or updating to values that exactly match a
                band already in the table is not allowed; that existing band
                is selected instead. <strong>Remove</strong> deletes
                the selected band(s) — Ctrl/Shift-click several rows first to
                remove more than one at a time.</td>
            <td>A narrow periodic noise spike (e.g. 50&nbsp;Hz mains coupling)
                visible as a sharp peak in the power spectrum.</td>
        </tr>
    </table>

    <div class="note">
        <strong>Frequency axis convention:</strong>
        The Quick cut spinboxes show values as a <em>percentage</em> of the
        Nyquist frequency: 0&nbsp;% = DC (constant offset),
        100&nbsp;% = Nyquist = half the sampling rate. The stop-bands table
        itself shows the same values already converted to the normalised
        0&ndash;1 scale it stores internally (and saves), so a 1&nbsp;%
        Quick cut appears in the table as <span class="fm">0.010</span>.
        For a spectrum with N uniformly-spaced points, a cutoff of
        <em>p</em>&nbsp;% corresponds to one full oscillation every
        <span class="fm">100 / p</span> data points.
    </div>

    <hr>
    <h2 id="preview">Preview tabs</h2>

    <table>
        <tr><th>Tab</th><th>Shows</th><th>When to use</th></tr>
        <tr>
            <td><strong>Power spectrum</strong></td>
            <td>Single-sided amplitude spectrum for the navigator spectrum.
                Filtered regions shaded red.</td>
            <td>Identify the frequency ranges occupied by baseline drift or
                noise before choosing cutoffs.</td>
        </tr>
        <tr>
            <td><strong>Signal preview</strong></td>
            <td>Selected spectra, original vs denoised.
                <em>Subplots</em> mode: stacked panels.
                <em>Overlay</em> mode: original (dashed) and denoised (solid)
                on one axes.</td>
            <td>Check that peaks are preserved and artefacts are removed.</td>
        </tr>
        <tr>
            <td><strong>Power + Signal</strong></td>
            <td>Power spectrum (left) and signal preview (right) simultaneously.
                Same view-mode toggle as Signal preview.</td>
            <td>Tune thresholds interactively while watching both effects
                without switching tabs.</td>
        </tr>
        <tr>
            <td><strong>All spectra — denoised</strong></td>
            <td>All list-selected spectra in their denoised form, overlaid.</td>
            <td>Confirm consistency across the whole dataset;
                spot outliers before applying.</td>
        </tr>
    </table>

    <p>The <strong>navigator (◀ / ▶)</strong> controls which single spectrum
    is shown in the <em>Power spectrum</em> and <em>Power&nbsp;+&nbsp;Signal</em>
    tabs. The spectra list selection controls which spectra appear in
    <em>Signal preview</em> and <em>All spectra&nbsp;— denoised</em>.</p>

    <hr>
    <h2 id="algorithm">Algorithm</h2>

    <div class="detail">
        <h3>Step-by-step</h3>
        <p><strong>1. Forward FFT:</strong><br>
        <span class="fm">Y = numpy.fft.rfft(y)</span><br>
        The real-input FFT produces N/2&nbsp;+&nbsp;1 complex coefficients.
        Normalised frequencies run from 0 (DC) to 0.5 (Nyquist); these are
        further scaled to [0,&nbsp;1] for display.</p>

        <p><strong>2. Build the mask:</strong><br>
        Start with a mask of all 1s. For each stop-band (including those implied
        by the scalar cutoffs), set mask[f_lo &le; f &le; f_hi] = 0.</p>

        <p><strong>3. Apply mask:</strong><br>
        <span class="fm">Y_filtered = Y &times; mask</span><br>
        Both real and imaginary parts of the complex coefficients are zeroed
        simultaneously &mdash; equivalent to the MATLAB treatment in
        <em>fnoise.m</em> which applied the same filter to the real and
        imaginary spectra independently before recombining.</p>

        <p><strong>4. Inverse FFT:</strong><br>
        <span class="fm">y_out = numpy.fft.irfft(Y_filtered, n=N)</span><br>
        The <span class="fm">irfft</span> call enforces Hermitian symmetry,
        guaranteeing a real-valued output without any imaginary artefacts.</p>
        <a class="back-link" href="#top">&#9650; back to top</a>
    </div>

    <hr>
    <h2 id="tips">Practical tips</h2>

    <div class="tip">
        <strong>Start with the power spectrum.</strong> Open the dialog and note
        where the amplitude is elevated near 0&nbsp;% (baseline) and near
        100&nbsp;% (noise floor). Your cutoffs should sit just inside the flat
        regions on each side, not inside the Raman band region.
    </div>

    <div class="warn">
        <strong>Over-filtering artefacts.</strong> Setting the high cutoff too
        low introduces ringing (Gibbs phenomenon) — oscillatory artefacts at
        sharp spectral features. If you see wavy baseline artefacts after
        denoising, raise the high cutoff. The Overlay view in the Signal panel
        makes this easy to spot.
    </div>

    <div class="warn">
        <strong>The frequency axis is data-point based, not wavenumber based.</strong>
        A cutoff of 1&nbsp;% means one full cycle per 100 data points,
        regardless of the wavenumber step. If you resample the spectrum (Data
        range with linearisation), the physical meaning of the cutoffs changes.
        Always inspect the power spectrum after any resampling step.
    </div>

    <div class="tip">
        <strong>Fine-tuning a Quick cut.</strong> Click Cut low or Cut high once
        to add the band, then select that row in the stop-bands table — its
        values load into F low/F high below where you can nudge them and click
        Update band, instead of clicking Cut low/high repeatedly.
    </div>

    <div class="tip">
        <strong>Baseline removal vs Quick cut Low.</strong> Both remove
        low-frequency content, but they work differently.
        Baseline correction fits and subtracts a smooth curve defined by
        user-placed points; Quick cut Low removes all energy below a uniform
        frequency threshold. For Raman spectra with broad fluorescence
        backgrounds, manual or automated baseline correction is usually more
        accurate. Quick cut Low is most useful for correcting mild, nearly
        sinusoidal drift (e.g. temperature-induced grating drift over a long scan).
    </div>

    <hr>
    <h2 id="faq">FAQ</h2>

    <h3>The denoised spectrum has strange oscillations near sharp peaks.</h3>
    <p>This is Gibbs ringing from too aggressive a high-cutoff (the rectangular
    window causes overshoot at discontinuities in frequency space). Raise the
    high cutoff and recheck. Mild ringing can also arise from a too-aggressive
    low cutoff near a band that spans a wide x-range.</p>

    <h3>How do I target 50 Hz / 60 Hz mains hum?</h3>
    <p>Convert the mains frequency to a normalised frequency:
    <span class="fm">f_norm = f_mains / (0.5 * sampling_rate)</span>,
    where the sampling rate is 1 / (wavenumber step in cm<sup>&minus;1</sup>
    if the spectrum is uniformly sampled). Add a narrow custom stop-band centred
    on this value, width ~0.01.</p>

    <h3>Does FFT denoising change peak positions or areas?</h3>
    <p>A correctly applied filter (high cutoff comfortably above the band
    frequencies, low cutoff comfortably below) does not shift peak positions
    or change integrated areas measurably. Always check the Overlay view to
    confirm this for your data before applying.</p>

    <h3>Can I apply different cutoffs to different spectra?</h3>
    <p>Not in the current version — the same filter is applied to all selected
    spectra. If spectra differ significantly in noise level, apply the operation
    in separate batches with different settings.</p>

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
