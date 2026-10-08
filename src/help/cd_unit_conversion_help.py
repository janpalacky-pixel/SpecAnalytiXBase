# src/help/cd_unit_conversion_help.py


def get_cd_unit_conversion_help_title():
    return 'CD Unit Conversion — help'


def get_cd_unit_conversion_help_content():
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

    <h1>CD Unit Conversion</h1>

    <p>CD (circular dichroism) spectropolarimeters — including the JASCO
    instruments read by this application's <strong>.jws</strong> and <strong>.jwb</strong> importers —
    report raw ellipticity in <strong>millidegrees (mdeg)</strong>. That raw
    reading is a physical property of the sample itself (like an ordinary
    UV/Vis absorbance reading), and it scales directly with concentration
    and path length — <span class="fm">&theta;_obs(mdeg) = 32980 &times;
    &Delta;&epsilon; &times; c[M] &times; l[cm]</span> (see
    <a href="#formulas">Formulas</a> below). So it is <em>not</em> directly
    comparable between samples of different concentration or between
    measurements made in different cuvettes (path lengths) &mdash; true even
    for the exact same molecule measured on the exact same instrument. This
    operation converts raw mdeg spectra into one of three standard,
    concentration- and path-length-independent quantities used throughout
    the CD literature:</p>

    <ul>
        <li><strong>Molar / mean-residue ellipticity [&theta;]</strong>
            (deg&middot;cm&sup2;&middot;dmol&#8315;&sup1;) &mdash; the most
            commonly plotted CD quantity, directly comparable between
            samples of different concentration, path length, and (for the
            mean-residue convention) even different molecule length.</li>
        <li><strong>Differential molar extinction coefficient &Delta;&epsilon;</strong>
            (M&#8315;&sup1;&middot;cm&#8315;&sup1;) &mdash; the CD analogue
            of a normal molar extinction coefficient; convenient when
            comparing directly against absorption spectroscopy. Also
            available on a molecular/per-strand or mean-residue/mean-
            nucleotide basis, exactly like [&theta;] (see
            <a href="#formulas">Formulas</a>).</li>
        <li><strong>Differential absorbance &Delta;A</strong> (dimensionless)
            &mdash; the raw absorbance difference between left- and
            right-circularly polarized light implied by the instrument
            reading, with no concentration or path length correction at all.</li>
    </ul>

    <div class="note">
        <strong>Typical pipeline position:</strong><br>
        Import (.jws, .jwb or other CD data) &rarr; Baseline correction / Data
        range &rarr; <strong>CD Unit Conversion</strong> &rarr; further
        analysis (SVD Analysis, 2D Correlation, Melting Curve Analysis&hellip;).<br>
        Convert units early, right after basic clean-up and before any
        analysis step that compares spectra across samples &mdash; comparing
        raw mdeg spectra of samples with different concentrations is not
        scientifically meaningful.
    </div>

    <div class="tip">
        <strong>No molecular weight needed in the common case.</strong>
        If you already know the concentration in a molar unit (M / mM /
        &micro;M) &mdash; for example, DNA/RNA concentration determined from
        A260 absorbance and a known/estimated extinction coefficient &mdash;
        none of the three outputs need a molecular weight at all. It's
        only asked for, and only matters, when concentration is entered as
        a mass concentration (mg/mL), purely to convert that to mol/L.
    </div>

    <hr>
    <h2>Workflow</h2>
    <ol>
        <li><strong>Select spectra</strong> &mdash; choose one or more raw
            mdeg CD spectra in the main window.</li>
        <li><strong>Open Parameters</strong> &mdash; click the Parameters
            button in the Spectra Processing panel to open the CD Unit
            Conversion dialog. It opens with one table row per selected
            spectrum.</li>
        <li><strong>Choose the concentration unit</strong> &mdash; M, mM,
            &micro;M, or mg/mL. This one setting applies to every row's
            Concentration column.</li>
        <li><strong>Fill in the table</strong> &mdash; Path length (cm) and
            Concentration for every row; Molecular weight too, but only if
            you chose mg/mL (the column is hidden otherwise). Type directly,
            or use the spreadsheet-style shortcuts below to fill many rows
            at once.</li>
        <li><strong>Choose the concentration basis</strong> (used for both
            the [&theta;] and &Delta;&epsilon; outputs, with the exception
            of &Delta;A) &mdash; <em>Molecular / per-strand (whole
            molecule)</em>, which needs nothing further, or <em>Mean-residue
            / mean-nucleotide</em>, which adds a <strong>Residues/Nucleotides
            (N)</strong> column to the table &mdash; a plain count, read
            directly from each spectrum's own sequence length, entered
            <em>per row</em> so a batch can freely mix molecules of
            different length.</li>
        <li><strong>Choose the output quantity</strong> &mdash; [&theta;],
            &Delta;&epsilon;, or &Delta;A.</li>
        <li><strong>Click Apply or Add as New</strong> &mdash; both commit
            immediately, with their own confirmation and result message
            shown right in the dialog; there is no separate Run step.</li>
    </ol>

    <div class="tip">
        <strong>Spreadsheet-style table shortcuts:</strong>
        <ul>
            <li>Type directly into any cell, or double-click to edit.</li>
            <li><strong>Ctrl+C</strong> / <strong>Ctrl+X</strong> / <strong>Ctrl+V</strong>
                copy, cut, and paste a selected block of cells &mdash; including
                pasting straight from an external spreadsheet.</li>
            <li>Pasting a <em>single</em> value while <em>several</em> cells
                are selected fills all of them with that one value &mdash; the
                fast way to give every spectrum the same path length, for
                example: copy one cell, click the column header to select
                the whole column, then paste.</li>
            <li><strong>Delete</strong> clears every selected cell.</li>
        </ul>
        <p>Every real CD experiment is different: sometimes every spectrum
        in a batch shares one path length and only concentration varies
        (e.g. a titration series); sometimes both vary from spectrum to
        spectrum. The table handles either case the same way &mdash; fill
        in whatever actually varies, and use paste-to-fill for whatever
        stays constant.</p>
    </div>

    <div class="tip">
        <strong>Apply vs. Add as New vs. Close:</strong>
        <ul>
            <li><strong>Apply</strong> replaces the selected spectra with
                their converted result.</li>
            <li><strong>Add as New</strong> leaves the originals untouched
                and adds the converted result under new, unique names
                (e.g. <span class="fm">samplename_ellipticity</span>,
                <span class="fm">samplename_deltaEpsilon</span>, or
                <span class="fm">samplename_deltaA</span> depending on the
                chosen output, with a number appended if that name is
                already taken).</li>
            <li><strong>Close</strong> closes the dialog without applying
                anything to the main window's spectra.</li>
        </ul>
    </div>

    <div class="warn">
        <strong>Only the concentration unit and basis are shared.</strong>
        Path length, concentration, molecular weight, and N (residue/
        nucleotide count) can all differ freely row by row &mdash; so a
        batch mixing different molecules of different lengths converts
        correctly in one pass. The <em>concentration unit</em> (M / mM /
        &micro;M / mg/mL) and the <em>concentration basis</em>
        (molecular/per-strand vs. mean-residue/mean-nucleotide) are the
        only two settings that apply to the whole table at once; if your
        selection genuinely mixes samples quantified in different
        concentration units, convert those in separate passes.
    </div>

    <hr>
    <h2 id="formulas">Formulas</h2>

    <p>All three output quantities are derived directly from the <em>molar</em>
    concentration c[M] and a single fixed instrument constant, so that for
    the same input spectrum and parameters they always agree with each
    other exactly. This is the standard normalisation used throughout CD
    spectroscopy for both proteins and nucleic acids — see
    <a href="#independent-definitions">Independent definitions of &Delta;A,
    &theta;, and &Delta;&epsilon;</a> and
    <a href="#where-32980-comes-from">Where does 32980 come from?</a> below
    for the full from-scratch derivation, openly available with no
    login/paywall required.</p>

    <div class="cat">
        <p><span class="fm">&Delta;A = &theta;_obs(mdeg) / 32980</span></p>
        <p><span class="fm">&Delta;&epsilon; whole-molecule (M&#8315;&sup1;cm&#8315;&sup1;) = &theta;_obs(mdeg) / (32980 &times; c[M] &times; l[cm])</span></p>
        <p><span class="fm">[&theta;] whole-molecule (deg&middot;cm&sup2;&middot;dmol&#8315;&sup1;) = &theta;_obs(mdeg) / (10 &times; l[cm] &times; c[M])</span></p>
        <p><span class="fm">&Delta;&epsilon; mean-residue = &Delta;&epsilon; whole-molecule / N</span></p>
        <p><span class="fm">[&theta;] mean-residue = [&theta;] whole-molecule / N</span>,
        where N is the number of residues (protein/peptide) or nucleotides
        (nucleic acid) in the molecule. <strong>The N division applies
        identically to &Delta;&epsilon; and [&theta;]</strong> &mdash; see
        below.</p>
        <p>where <em>l</em> is the path length and <em>c[M]</em> is the
        concentration in mol/L (per whole molecule/strand for the molecular
        basis, or already multiplied by N for the mean-residue basis &mdash;
        this application takes care of that by dividing the whole-molecule
        result by N instead, which is exactly equivalent). None of these
        need a molecular weight — only the molar concentration, path
        length, and (for the mean-residue basis) the residue/nucleotide
        count N.</p>
    </div>

    <p>These formulas are mutually consistent:
    <span class="fm">[&theta;] = 3298 &times; &Delta;&epsilon;</span>
    (since 32980&nbsp;&divide;&nbsp;10&nbsp;=&nbsp;3298 exactly), and this
    identity holds <strong>regardless of which concentration basis</strong>
    was used to compute both sides — whole-molecule [&theta;] equals 3298
    times whole-molecule &Delta;&epsilon;, and mean-residue [&theta;]
    equals 3298 times mean-residue &Delta;&epsilon;, in exactly the same
    way. That's why choosing the mean-residue/mean-nucleotide basis divides
    <em>both</em> [&theta;] and &Delta;&epsilon; by N, not just [&theta;]:
    dividing the concentration term by N divides whichever quantity is
    computed from it by that same N, before the fixed 3298 factor is ever
    applied. <span class="fm">&Delta;A</span> is the raw,
    concentration-independent quantity everything else is built from — the
    concentration basis has no effect on it at all. The instrument constant
    32980 is the commonly cited value in the CD literature (sometimes given
    more precisely as 32982, or 32.982 for &theta; in whole degrees rather
    than millidegrees — see <a href="#where-32980-comes-from">Where does
    32980 come from?</a>); 32980 is used throughout this operation
    specifically so the outputs never disagree with each other by a
    fraction of a percent for no physical reason.</p>

    <div class="note">
        <strong>Is "[&theta;] = 3298 &times; &Delta;&epsilon;" just algebra?</strong>
        Read on its own, yes &mdash; if two quantities are both defined as
        the same raw &theta;_obs divided by two different constants (10 and
        32980), then of course their ratio is fixed at 32980&divide;10, for
        any &theta;_obs, c, l, or N. That part carries no physics; it's
        bookkeeping. The actual physical claim is one level underneath it,
        in <a href="#independent-definitions">Independent definitions</a>
        below: &Delta;&epsilon; and &theta; each have their own definition
        from a <em>completely different kind of measurement</em> &mdash;
        &Delta;&epsilon; from an ordinary two-beam absorbance difference,
        &theta; from the geometry of a polarization ellipse, with neither
        definition referring to the other at all. That these two
        independently-defined, independently-measurable quantities turn out
        to be proportional, with specifically the 32980 constant, is the
        real (derivable, falsifiable) physics &mdash; see
        <a href="#where-32980-comes-from">Where does 32980 come from?</a>
        for that derivation. Once that one fact is granted, everything else
        on this page, including this 3298 identity holding under any
        concentration basis, really is just algebra built on top of it.
    </div>

    <h3 id="independent-definitions">Independent definitions of &Delta;A, &theta;, and &Delta;&epsilon;</h3>
    <p>The formulas above convert between these three quantities, which can
    make it look like one is just an algebraic rearrangement of another.
    It isn't — each has its own independent physical definition, and they
    only turn out to be numerically tied together (see
    <a href="#where-32980-comes-from">below</a>) because of how the physics
    of polarized light happens to work out.</p>

    <div class="cat">
        <p><strong>&Delta;A &mdash; differential absorbance.</strong> The
        fundamental definition of circular dichroism: shine left-circularly-
        polarized (L-CP) and right-circularly-polarized (R-CP) light through
        the sample and measure each beam's ordinary Beer-Lambert absorbance
        separately:</p>
        <p><span class="fm">A_L = log&#8321;&#8320;(I&#8320; / I_L)</span>,
        &nbsp; <span class="fm">A_R = log&#8321;&#8320;(I&#8320; / I_R)</span></p>
        <p><span class="fm">&Delta;A = A_L &minus; A_R</span></p>
        <p>the same kind of quantity as an ordinary UV/Vis absorbance
        reading &mdash; just the difference between two absorbance
        measurements made with opposite circular polarizations, in
        arbitrary absorbance units (AU). Nothing about this definition
        refers to &theta; or &Delta;&epsilon;.</p>

        <p><strong>&Delta;&epsilon; &mdash; molar circular dichroism
        (differential molar extinction coefficient).</strong> Each
        polarization obeys the ordinary Beer-Lambert law with its own molar
        extinction coefficient:</p>
        <p><span class="fm">A_L = &epsilon;_L &middot; c &middot; l</span>,
        &nbsp; <span class="fm">A_R = &epsilon;_R &middot; c &middot; l</span></p>
        <p><span class="fm">&Delta;&epsilon; = &epsilon;_L &minus; &epsilon;_R = &Delta;A / (c &middot; l)</span></p>
        <p>&epsilon;_L and &epsilon;_R are ordinary molar extinction
        coefficients (M&#8315;&sup1;cm&#8315;&sup1;), the same physical
        quantity used in any UV/Vis absorption measurement.
        &Delta;&epsilon; is simply their difference &mdash; an intrinsic
        molecular property that, unlike &Delta;A, doesn't depend on
        concentration or path length.</p>

        <p><strong>&theta; &mdash; ellipticity.</strong> A purely optical,
        geometric quantity, defined with no reference to absorbance at all.
        Linearly polarized light can be decomposed into two equal-amplitude
        L-CP and R-CP components. If the sample absorbs one component more
        than the other, the two components recombine on the far side with
        <em>unequal</em> amplitudes, and the emergent light is no longer
        linearly polarized — it traces out an ellipse. &theta; is the angle
        whose tangent is the ratio of that ellipse's minor to major axis:</p>
        <p><span class="fm">tan &theta; = (E_R &minus; E_L) / (E_R + E_L)</span></p>
        <p>where E_R and E_L are the electric-field amplitudes of the two
        components after the sample. This is exactly what a polarimeter
        measures directly (historically via null-detection optics), and by
        itself has nothing to do with absorbance or extinction
        coefficients.</p>
    </div>

    <p>So &Delta;A/&Delta;&epsilon; and &theta; describe the very same
    physical effect from two different angles: &Delta;A and &Delta;&epsilon;
    treat CD as an <em>absorption</em> phenomenon (a differential absorbance
    between two polarizations, exactly like ordinary UV/Vis spectroscopy),
    while &theta; treats it as a <em>polarization</em> phenomenon (distortion
    of a light beam's polarization ellipse). They end up numerically tied
    together only because intensity is proportional to the square of field
    amplitude (I &prop; E&sup2;), which links the amplitude ratio that
    defines &theta; to the absorbance difference that defines &Delta;A —
    worked out explicitly below. Modern instruments actually measure
    intensities (equivalently, &Delta;A) directly and compute &theta; from
    that, purely to stay compatible with the older polarimetric literature
    where &theta; was the quantity historically measured.</p>

    <h3 id="where-32980-comes-from">Where does 32980 come from?</h3>
    <p>It isn't an empirical CD-literature convention &mdash; it drops
    straight out of the definition of "ellipticity" itself. CD instruments
    historically report an <em>ellipticity angle</em> &theta; rather than
    &Delta;A directly, defined by how much a beam of linearly polarized
    light gets distorted into an ellipse: tan&thinsp;&theta; = (E_R &minus;
    E_L)/(E_R + E_L), the ratio of the electric-field amplitudes of the
    right- and left-circularly-polarized components. Since intensity is
    proportional to E&sup2;, converting absorbances to field amplitudes
    (E &prop; 10<sup>&minus;A/2</sup>) via Beer-Lambert and expanding for
    small &Delta;A gives &theta;(radians) &asymp; (ln&thinsp;10/4)&middot;&Delta;A.
    Converting radians to degrees:</p>
    <div class="cat">
        <p><span class="fm">&theta;(degrees) = &Delta;A &times; (ln 10 / 4) &times; (180 / &pi;) &asymp; &Delta;A &times; 32.982</span></p>
    </div>
    <p>In millidegrees that's &times;1000, giving the 32980&ndash;32982
    used throughout the CD literature (different sources round
    differently). The molar-ellipticity formula's "10" has the same kind
    of origin: the textbook definition is [&theta;] = 100&middot;&theta;
    (degrees)/(c&middot;l) &mdash; the 100 is a fixed units-conversion
    factor (path length cm&rarr;m, mol&rarr;decimol) that produces the
    conventional deg&middot;cm&sup2;&middot;dmol&#8315;&sup1; unit; dividing
    by another 1000 for millidegrees gives the 10 in this operation's
    formula. The 3298 ratio between [&theta;] and &Delta;&epsilon; (32980
    &divide; 10) is then just algebra on these two definitions, not an
    independent assumption &mdash; which is also why it applies identically
    whether the concentration used is whole-molecule or mean-residue (see
    above).</p>
    <p>For a from-scratch derivation with no login/paywall required, see
    Applied Photophysics' <a href="https://www.photophysics.com/faqs/methods-techniques/cd-units-faqs/">CD
    Units FAQ</a> (a CD instrument manufacturer's reference page), which
    independently states both the 32.982 relationship and confirms the
    mean-residue case explicitly: <em>"[&theta;]<sub>MR</sub> = 100&middot;&theta;/(l&middot;c&middot;N)
    = 3298.2&middot;&Delta;&epsilon;<sub>MR</sub> = 3298.2&middot;&Delta;A/(l&middot;c&middot;N)."</em></p>

    <h3>If concentration is only known in mg/mL</h3>
    <p>If you don't already have a molar concentration, you can instead
    enter concentration in mg/mL together with the molecular weight (g/mol
    &mdash; the same number as Da, just a different name for the same unit).
    The molecular weight is used <em>only</em> to convert the mass
    concentration to a molar one:
    <span class="fm">c[M] = c[mg/mL] / MW[g/mol]</span>. Once that
    conversion is done, the same formulas above apply, using the resulting
    c[M] &mdash; the molecular weight itself never appears anywhere else in
    the calculation.</p>

    <hr>
    <h2 id="settings">Settings reference</h2>

    <table>
        <tr>
            <th>Setting</th>
            <th>Description</th>
        </tr>
        <tr>
            <td><strong>Path length</strong> (table column)</td>
            <td>Cuvette path length in cm, entered per spectrum. Common
                values: 0.1&nbsp;cm (concentrated samples, far-UV), 1.0&nbsp;cm
                (dilute samples, near-UV/visible). Greyed out when the
                output is &Delta;A, which doesn't need it.</td>
        </tr>
        <tr>
            <td><strong>Concentration</strong> (table column)</td>
            <td>Sample concentration of the whole molecule, entered per
                spectrum, in whichever unit is selected above the table
                (M, mM, &micro;M, or mg/mL &mdash; applies to every row).
                Not required for &Delta;A output.</td>
        </tr>
        <tr>
            <td><strong>Molecular weight</strong> (table column)</td>
            <td>Only shown, and only used, when the concentration unit is
                mg/mL &mdash; purely to convert that row's mass concentration
                to mol/L (g/mol; numerically identical to Da). Hidden
                entirely for the M / mM / &micro;M units. Doesn't replace
                the Concentration column &mdash; both are required together
                when the unit is mg/mL.</td>
        </tr>
        <tr>
            <td><strong>Concentration basis</strong></td>
            <td><em>Molecular / per-strand (whole molecule)</em> &mdash;
                needs nothing beyond concentration and path length;
                appropriate when comparing samples of the identical
                molecule, and the basis recommended for oligonucleotides of
                precisely known length. <em>Mean-residue / mean-nucleotide</em>
                &mdash; divides the whole-molecule result by the residue/
                nucleotide count N, entered per row in the table; the
                standard convention for comparing proteins or nucleic acids
                of <em>different length</em>. Affects <strong>both</strong>
                the [&theta;] and &Delta;&epsilon; outputs identically (see
                <a href="#formulas">Formulas</a>) — meaningless for
                &Delta;A, which never uses concentration.</td>
        </tr>
        <tr>
            <td><strong>Residues/Nucleotides (N)</strong> (table column)</td>
            <td>Only shown, and only used, with the mean-residue basis. The
                number of amino-acid residues (protein/peptide) or
                nucleotides (DNA/RNA) in <em>that row's</em> molecule
                &mdash; read directly from its sequence length. Entered per
                spectrum, so a batch can mix molecules of different length.
                No molecular weight is involved in this step.</td>
        </tr>
        <tr>
            <td><strong>Convert to</strong></td>
            <td>The output quantity: [&theta;], &Delta;&epsilon;, or &Delta;A
                (see <a href="#formulas">Formulas</a> above).</td>
        </tr>
    </table>

    <hr>
    <h2 id="output">Output</h2>

    <p>After clicking <strong>Apply</strong> or <strong>Add as New</strong>:</p>
    <ul>
        <li>Each converted spectrum's <span class="fm">y_scale</span> is
            replaced with the chosen output quantity. Use <strong>Add as
            New</strong> instead of Apply if you want to keep the original
            raw-mdeg spectrum around as a separate entry alongside the
            converted result.</li>
        <li>A <span class="fm">cd_conversion_info</span> dict is stored in
            each spectrum recording the output type, path length,
            concentration, and (when applicable) the molecular weight
            and/or residue count used.</li>
        <li>The operation is registered in the pipeline history and can be
            reviewed in the <strong>Summary</strong> dialog.</li>
    </ul>

    <div class="note">
        <strong>Y-axis label:</strong> this operation does not automatically
        rename the plot's y-axis label. After converting, update it manually
        (e.g. via the plot's axis properties) to match the new quantity and
        unit, e.g. "[&theta;] (deg&middot;cm&sup2;&middot;dmol&#8315;&sup1;)".
    </div>

    <hr>
    <h2 id="faq">Frequently asked questions</h2>

    <h3>Same sample, same cuvette, but measured on two different
    instruments &mdash; will the raw mdeg reading differ?</h3>
    <p>Not in principle. &theta;_obs (the mdeg reading) is a physical
    property of the sample and cuvette &mdash; the same kind of quantity as
    an ordinary UV/Vis absorbance reading &mdash; not an arbitrary
    instrument-specific number. Two correctly calibrated instruments
    measuring the same sample in the same cuvette should read the same
    &theta;_obs, just as two correctly calibrated UV/Vis spectrophotometers
    should agree on absorbance for the same sample.</p>
    <p>In practice, small differences between instruments do happen, but for
    a different reason than "different optics" as such: imperfect or
    differing calibration (CD instruments are calibrated against a
    reference standard, e.g. camphorsulfonic acid), detector/PMT linearity
    and HT (dynode voltage) behaviour, monochromator bandwidth, and stray
    light. That is instrument calibration error / reproducibility &mdash;
    a real, separate issue this operation has no way to correct for. CD
    Unit Conversion only removes the concentration &times; path-length
    scaling shown under <a href="#formulas">Formulas</a>; it does not, and
    cannot, correct for one instrument disagreeing with another.</p>

    <h3>My spectra aren't in millidegrees &mdash; can I still use this?</h3>
    <p>This operation assumes the input y-values are raw ellipticity in
    millidegrees, the standard raw output of a CD spectropolarimeter (and
    what this application's .jws and .jwb importers read for the CD channel). If
    your spectra are already in absorbance units or some other quantity,
    converting them here will give an incorrect result &mdash; use
    <strong>Spectral Calculator</strong> instead, which can reproduce this
    operation's exact arithmetic for a formula you type yourself, e.g.
    <span class="fm">MySpectrum / (32980 * concentration * path_length)</span>
    for whole-molecule &Delta;&epsilon;, with the numeric concentration and
    path length typed directly into the formula. Two differences from this
    dialog: there is no per-spectrum table, so a spectrum with different
    concentration/path length needs its own formula (typed with that
    spectrum's own numbers) rather than one shared run across many rows;
    and Spectral Calculator has no built-in awareness of CD unit
    conventions &mdash; it only evaluates whatever arithmetic you write.</p>

    <h3>Why does &Delta;A output ignore concentration and path length?</h3>
    <p>&Delta;A is the raw absorbance difference implied directly by the
    instrument's millidegree reading &mdash; it is, by definition, what the
    instrument measured before any sample-specific normalization. Molar
    ellipticity and &Delta;&epsilon; both normalize this raw signal by
    concentration and path length so that different samples become
    directly comparable; &Delta;A intentionally does not.</p>

    <h3>How do Molecular weight and N work together for the mean-residue basis with mg/mL?</h3>
    <p>As two completely independent numbers used for two different
    purposes &mdash; exactly as you'd expect, nothing more subtle than
    that. When the concentration unit is mg/mL and the mean-residue basis
    is selected, this operation does exactly two separate steps:</p>
    <ol>
        <li><strong>Molecular weight</strong> converts that row's mg/mL
        entry into a whole-molecule molar concentration:
        <span class="fm">c[M] = c[mg/mL] / MW[g/mol]</span>. This step
        alone gives the same molar concentration you'd have entered
        directly if you'd used M/mM/&micro;M instead of mg/mL &mdash; it
        has nothing to do with N.</li>
        <li>Whichever concentration unit was used, if the mean-residue
        basis is selected, the resulting [&theta;] or &Delta;&epsilon; is
        then divided by <strong>N</strong> (a count of residues/
        nucleotides, not a weight) &mdash; the same division described
        under <a href="#formulas">Formulas</a> above, unrelated to how the
        molar concentration was obtained in step 1.</li>
    </ol>
    <p>So yes &mdash; compute the molar concentration from Molecular
    weight, then separately divide by N. That's precisely what this
    operation does; there's no hidden relationship between the two
    numbers to worry about.</p>
    <p>The one thing worth knowing: some older CD workflows skip step 1's
    ordinary molecular weight entirely and instead ask for a single "mean
    residue weight" (MRW = molecular weight &divide; N) to go straight
    from mg/mL to a per-residue concentration in one step, rather than
    two. That gives the exact same final answer, but requires looking up
    or computing MRW yourself first. Entering the molecule's normal
    molecular weight and N as two separate, independently-meaningful
    values (as this dialog does) needs nothing extra to look up.</p>

    <h3>Does the mean-residue/mean-nucleotide basis apply to &Delta;&epsilon; too, or only [&theta;]?</h3>
    <p><strong>Both.</strong> [&theta;] = 3298 &times; &Delta;&epsilon; is
    an identity that holds no matter which concentration basis was used to
    compute both sides, so dividing by N to get a per-residue/per-nucleotide
    value applies identically to &Delta;&epsilon; and [&theta;] &mdash; see
    <a href="#formulas">Formulas</a> for the full derivation. This can be
    verified independently from the open, no-login
    <a href="https://www.photophysics.com/faqs/methods-techniques/cd-units-faqs/">CD
    Units FAQ</a> cited under <a href="#where-32980-comes-from">Where does
    32980 come from?</a>, which gives the mean-residue relation explicitly
    as [&theta;]<sub>MR</sub> = 3298.2&middot;&Delta;&epsilon;<sub>MR</sub>
    &mdash; the same 3298.2 factor, applied to the mean-residue value of
    both quantities.</p>

    <h3>I don't have a molar concentration — only mg/mL. What do I do?</h3>
    <p>Switch the concentration unit to mg/mL and enter both the
    Concentration (in mg/mL) and the Molecular weight — the Molecular
    weight column re-appears automatically. The molecular weight is used
    once per row, purely to convert that row's mg/mL value to mol/L;
    everything downstream then works exactly as it would if you'd entered
    the molar concentration directly.</p>

    <h3>If I enter a molecular weight, do I still need to fill in Concentration?</h3>
    <p>Yes, always. Molecular weight is a property of the molecule — it
    never varies with how much of it is in solution — while Concentration
    is how much sample is actually present. They answer two different
    questions, so entering one is never a substitute for the other. When
    the concentration unit is mg/mL, both columns are required together
    (Concentration &divide; Molecular weight = molar concentration); for
    the molar units (M / mM / &micro;M) only Concentration is needed and
    the Molecular weight column is hidden entirely.</p>

    <h3>Can I convert spectra that were already converted once?</h3>
    <p>Yes, but be careful: running this operation again on an already-
    converted spectrum (rather than on the original raw mdeg data) will
    apply the formula to values that are no longer in millidegrees,
    producing a scientifically meaningless result. Use <strong>Add as
    New</strong> the first time so the original raw spectrum is preserved
    for any future re-conversion with different parameters.</p>

    <h3>Different concentrations, path lengths, or molecule lengths per spectrum?</h3>
    <p>That's the normal case, not a special one &mdash; every row of the
    table has its own Path length, Concentration, Molecular weight (if
    used), and Residues/Nucleotides N (if used), so a titration series, a
    batch of samples each measured at a different path length, or a mixed
    batch of different-length proteins/nucleic acids all convert correctly
    in a single Apply / Add as New. See the spreadsheet-style shortcuts
    under <a href="#top">Workflow</a> above for filling many rows quickly.</p>

    <h2>Spectrum Names in the Table</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox &mdash; separate from the main window's, and off by default
    regardless of the main window's setting &mdash; which the table's
    Spectrum column follows. This is purely a display change &mdash; it never
    affects which spectrum a row belongs to, what gets saved into the
    per-spectrum settings, or what a copy/paste or "Add as New" name is
    built from, all of which always use each spectrum's full, original
    label/unique ID regardless of what's currently shown on screen.</p>

    </body>
    </html>
    """
