# src/help/xaxis_unit_conversion_help.py


def get_xaxis_unit_conversion_help_title():
    return 'X-axis Unit Conversion — help'


def get_xaxis_unit_conversion_help_content():
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

    <h1>X-axis Unit Conversion</h1>

    <p>Converts a spectrum's x-axis between the four standard units used
    across UV-Vis, CD/ECD, and general optical spectroscopy:
    wavelength (nm), wavenumber (cm&#8315;&sup1;), energy (eV), and
    frequency (Hz). Each is an exact, parameter-free physics formula
    &mdash; no concentration, path length, or instrument constant is
    involved, unlike CD Unit Conversion. The y-values are never touched;
    only the x-axis changes.</p>

    <div class="note">
    <p><strong>Where this is useful for CD/ECD work:</strong> comparing an
    experimental band position (typically reported in nm) against a
    computed transition energy from a quantum-chemistry calculation
    (TD-DFT and similar methods report transition energies in eV, not
    nm) &mdash; convert one to the other's unit to check whether they
    line up. It's also useful for overlaying/comparing a spectrum
    recorded on a wavenumber axis against one recorded on a wavelength
    axis.</p>
    </div>

    <hr>
    <h2 id="formulas">Formulas</h2>

    <p>All four units are related to wavelength through simple
    reciprocal relationships. This operation always goes through
    wavelength (nm) as an intermediate step, even when neither the
    source nor destination unit is wavelength itself (e.g. converting
    cm&#8315;&sup1; directly to eV goes cm&#8315;&sup1; &rarr; nm &rarr; eV
    internally) &mdash; the result is identical to a direct formula
    either way, since these are exact algebraic identities, not
    approximations.</p>

    <div class="cat">
        <p><span class="fm">wavenumber (cm&#8315;&sup1;) = 10,000,000 / wavelength (nm)</span></p>
        <p><span class="fm">energy (eV) = 1239.8419843320025 / wavelength (nm)</span></p>
        <p><span class="fm">frequency (Hz) = 299,792,458,000,000,000 / wavelength (nm)</span></p>
    </div>

    <p>Each relation is its own inverse (e.g.
    <span class="fm">wavelength (nm) = 10,000,000 / wavenumber (cm&#8315;&sup1;)</span>),
    since the same constant appears on both sides of a reciprocal
    relationship.</p>

    <h3 id="where-constants-come-from">Where do these constants come from?</h3>
    <p>All three are built from the SI's <em>exactly defined</em> physical
    constants (the 2019 redefinition of the SI base units made the Planck
    constant <span class="fm">h</span>, the speed of light
    <span class="fm">c</span>, and the elementary charge
    <span class="fm">e</span> exact by definition, not measured
    quantities with uncertainty):</p>
    <ul>
        <li><span class="fm">h = 6.62607015 &times; 10&#8315;&sup3;&#8308; J&middot;s</span> (exact)</li>
        <li><span class="fm">c = 299,792,458 m/s</span> (exact)</li>
        <li><span class="fm">e = 1.602176634 &times; 10&#8315;&sup1;&#8313; C</span> (exact)</li>
    </ul>
    <p>A photon's energy is <span class="fm">E = h&middot;c / &lambda;</span>
    (wavelength in metres). Converting to eV (dividing by <span class="fm">e</span>)
    and to nanometres (multiplying the wavelength by 10&#8313;) gives the
    widely tabulated constant
    <span class="fm">h&middot;c/e = 1239.8419843320025 eV&middot;nm</span>
    used above &mdash; exact to floating-point precision, not an
    approximation. The wavenumber relation
    (<span class="fm">1 cm = 10,000,000 nm</span>) is a plain unit
    conversion, and the frequency relation is
    <span class="fm">f = c / &lambda;</span> with <span class="fm">c</span>
    expressed in nm/s.</p>

    <hr>
    <h2 id="worked-example">Worked example</h2>
    <p>An experimental ECD band is observed at 280 nm. A TD-DFT
    calculation predicts the corresponding transition at 4.43 eV. Are
    they consistent?</p>
    <div class="cat">
        <p><span class="fm">280 nm &rarr; 1239.8419843320025 / 280 = 4.428 eV</span></p>
    </div>
    <p>4.428 eV vs. the calculated 4.43 eV &mdash; a good match. Converting
    the experimental nm value to eV (or the calculated eV value to nm)
    makes the comparison direct, instead of needing to cross-reference a
    conversion table by hand.</p>

    <hr>
    <h2 id="ascending-x">Why do the x-values sometimes get reordered?</h2>
    <p>This application requires every spectrum's x-axis to be ascending
    (left to right) &mdash; every operation that touches x/y pairs
    (smoothing, derivatives, baselines, peak finding, interpolation, and
    more) assumes it. Wavelength, wavenumber, energy, and frequency are
    all <em>inversely</em> related to each other: as wavelength goes up,
    the other three go down. So converting an ascending wavelength axis
    to wavenumber, energy, or frequency produces a <em>descending</em>
    axis &mdash; this operation automatically re-sorts the converted
    x/y pairs back to ascending order (the same points, just read left to
    right in the new unit), exactly like the one-time reordering this
    application already performs on import for any file with an
    out-of-order x-axis. Converting between two units that both increase
    together (e.g. cm&#8315;&sup1; &harr; eV, which are directly
    proportional) does not require reordering.</p>

    <hr>
    <h2 id="not-covered">What this operation does NOT do</h2>
    <div class="warn">
    <p><strong>Raman shift conversion is intentionally not supported.</strong>
    Raman shift (cm&#8315;&sup1;, measured relative to the excitation
    laser) is a different quantity from absolute wavelength, and
    converting between them needs the exact excitation laser wavelength
    as an extra input &mdash; a real number you'd have to know and enter,
    not a fixed physical constant like the ones above. More importantly,
    that conversion is only as accurate as the spectrometer's own
    wavelength axis calibration, which this software has no way to
    verify or correct (true wavelength calibration against a reference
    source, e.g. a neon lamp or a silicon standard, is a metrology
    procedure performed by the instrument or its vendor software, not
    something this application can do after the fact). If your Raman
    data's x-axis isn't reliably calibrated to begin with, converting it
    here would just propagate that inaccuracy under a different unit
    label. This may be added as a future, separate feature once a way to
    handle that calibration question properly is worked out.</p>
    </div>

    <hr>
    <h2 id="faq">Frequently asked questions</h2>

    <h3>Why does the operation reject some of my spectra?</h3>
    <p>All four supported units (wavelength, wavenumber, energy,
    frequency) are strictly positive physical quantities, and every
    conversion here involves a reciprocal (1/x) at some point in the
    calculation &mdash; undefined at zero, and not physically meaningful
    for a negative value. If any x-axis value in a selected spectrum is
    zero or negative, that spectrum is rejected with a message naming it,
    rather than silently producing an infinite or nonsensical value.</p>

    <h3>Can I convert a spectrum that's already been converted once?</h3>
    <p>Yes. Every conversion IS recorded in Operations History, like any
    other operation in this application &mdash; but this operation itself
    doesn't read that history back to figure out what unit the x-axis is
    currently in, or to stop you from converting it again. It always
    trusts whatever "From" unit you select, applied to whatever raw
    numbers are currently in the x-axis, regardless of what Operations
    History says was done before. So it's up to you to make sure the
    "From" unit you select actually matches what the spectrum's x-axis
    currently represents (check Operations History if you're not sure) —
    picking the wrong one produces a numerically valid but physically
    meaningless result. Use <strong>Add as New</strong> if you want to
    keep the original alongside the converted copy.</p>

    <h3>What if I pick the same unit for both From and To?</h3>
    <p>The spectrum is returned unchanged (a confirmation prompt warns you
    first, in case that wasn't intentional).</p>

    <hr>
    <p class="back-link"><a href="#top">Back to top</a></p>
    </body>
    </html>
    """
