# src/help/spectral_calculator_help.py

def get_spectral_calculator_help_title():
    return "Spectral Calculator Help"

def get_spectral_calculator_help_content():
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2 { color: #1976D2; margin-top: 25px; }
            h3 { color: #F57C00; margin-top: 18px; }
            .tip  { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .warn { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .code { background-color: #f5f5f5; font-family: 'Courier New', monospace;
                    padding: 8px; border-radius: 4px; margin: 6px 0; border-left: 3px solid #1976D2; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background-color: #E3F2FD; color: #1976D2; padding: 6px 10px; text-align: left; }
            td    { padding: 5px 10px; border-bottom: 1px solid #E0E0E0; }
            tr:nth-child(even) { background-color: #F8F9FB; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
        </style>
    </head>
    <body>
        <h1>Spectral Calculator Help</h1>

        <h2>Overview</h2>
        <p>The Spectral Calculator creates one or more new spectra by evaluating a
        user-defined mathematical formula. Spectrum labels from the main window are
        used directly as variable names in the formula. Unlike Combine Spectra
        (fixed average/sum), the calculator accepts any combination of operations,
        constants, and built-in spectroscopic functions, and can produce several
        output spectra from a single formula.</p>

        <div class="tip">
            <strong>Key difference from Combine Spectra:</strong> the calculator
            accepts arbitrary formulas, and a live preview shows the result as you type.
        </div>

        <div class="warn">
            <strong>All spectra must share an identical x-axis.</strong> The calculator
            does <em>not</em> interpolate spectra with different x-axes onto a common
            grid — if the selected spectra don't already match exactly, validation
            fails with an error telling you which two spectra differ. Use
            <strong>Define Spectral Range</strong> with <em>Apply linearisation</em>
            first to bring all spectra onto an identical x-axis before using the
            calculator.
        </div>

        <h2>How to Use</h2>
        <ol>
            <li>Select two or more spectra in the main window.</li>
            <li>Choose <em>Spectral Calculator</em> from the Spectra Processing dropdown
                and click <strong>Parameters</strong>.</li>
            <li>Type a formula in the formula box, or click an alias / function
                name in the reference panel to insert it at the cursor (see
                "Spectrum Variables" below for what the aliases mean). The
                <strong>Preview</strong> panel below the formula updates automatically
                as you type, showing the resulting spectrum (or spectra).</li>
            <li>Click <strong>Validate formula</strong> to check for errors before
                applying — this also reports how many output spectra the formula
                produces.</li>
            <li>Set a name for the result spectrum.</li>
            <li>Click <strong>Apply</strong> to replace the source spectra with the
                result(s), or <strong>Add as New</strong> to keep the sources and add
                the result(s) as new entries instead — this dialog's own buttons, the
                same Apply / Add as New choice used by every other operation. The
                dialog closes itself once the commit succeeds.</li>
        </ol>

        <div class="tip">
            <strong>Save without running:</strong> the <strong>Save&hellip;</strong>
            button exports whatever the Preview is currently showing
            directly to a file (table or individual spectra), without applying the
            operation to the main spectrum list or closing this dialog &mdash; useful
            for checking a result on disk before committing to it, or for keeping a
            one-off calculation that doesn't need to become a permanent entry in the
            spectrum list.
        </div>

        <h2>The Preview Panel</h2>
        <p>The Preview panel below the formula box shows the live result as you type,
        and offers several display controls:</p>
        <ul>
            <li><strong>Resizing:</strong> drag the divider between the formula/output
                area and the Preview panel to give either more room. The dialog window
                itself can also be maximized via its title bar.</li>
            <li><strong>Right-click on the plot</strong> to open a context menu with:
                <ul>
                    <li><em>Plot style</em> &mdash; Line, Points, or Points + line.</li>
                    <li><em>Log scale (X axis)</em> / <em>Log scale (Y axis)</em> &mdash;
                        toggle either axis to a logarithmic scale. Points with zero or
                        negative values are omitted from that axis while a log scale is
                        active, since a logarithm of zero or a negative number isn't
                        defined.</li>
                    <li><em>Open preview in external window</em> &mdash; opens the
                        current preview in a separate, resizable, non-modal window so
                        it can be compared side-by-side with other windows. The external
                        window has its own independent style/scale settings and its own
                        right-click menu (without the "open externally" option, since
                        that window already is the external view).</li>
                </ul>
            </li>
            <li>The built-in matplotlib toolbar above the plot still provides zoom,
                pan, and "save as image" as usual.</li>
        </ul>

        <h2>Writing Formulas</h2>

        <h3>Spectrum Variables (Aliases)</h3>
        <p>Real spectrum names can be long (e.g. <em>"Raman spectra - no header :
        0008"</em>), which makes them awkward to read and type inside a formula. To
        avoid this, the calculator assigns each selected spectrum a short alias —
        <strong>sp1</strong>, <strong>sp2</strong>, <strong>sp3</strong>, and so on, in
        the order the spectra were selected — and formulas are written using these
        aliases instead of the real names.</p>
        <div class="code">2 * sp1 + sp2 - sp3</div>
        <p>The reference panel on the right lists every selected spectrum as
        <em>alias &mdash; real name</em> (e.g. "sp1 &mdash; Raman spectra - no header :
        0008"), and hovering over an entry shows the same mapping as a tooltip, so it's
        always clear which real spectrum an alias refers to.</p>
        <div class="tip">
            <strong>Tip:</strong> Click an alias in the right-hand panel to insert it at
            the cursor rather than typing it manually.
        </div>
        <div class="warn">
            <strong>Aliases only exist inside this dialog.</strong> The real spectrum
            names are what actually get used for the calculation, what gets saved if
            you reopen Parameters later, and what appears in the result spectrum's
            metadata. Aliases are purely a typing/reading convenience and have no effect
            on the application outside this one dialog session. If you select a
            different set of spectra next time you open the calculator, the aliases are
            reassigned (sp1 is whichever spectrum was selected first that time) — they
            are not a permanent renaming of anything.
        </div>

        <h3>Basic Arithmetic</h3>
        <table>
            <tr><th>Operator</th><th>Meaning</th><th>Example</th></tr>
            <tr><td>+</td><td>Addition</td><td>sp1 + sp2</td></tr>
            <tr><td>-</td><td>Subtraction</td><td>sp1 - sp2</td></tr>
            <tr><td>*</td><td>Multiplication</td><td>2.5 * sp1</td></tr>
            <tr><td>/</td><td>Division</td><td>sp1 / sp2</td></tr>
            <tr><td>**</td><td>Power / exponentiation</td><td>sp1 ** 2</td></tr>
        </table>

        <h3>Built-in Functions</h3>
        <table>
            <tr><th>Function</th><th>Description</th><th>Spectroscopic use</th></tr>
            <tr><td>abs(x)</td><td>Absolute value</td><td>Remove negative artefacts</td></tr>
            <tr><td>sqrt(x)</td><td>Square root</td><td>Noise reduction, Kubelka-Munk linearisation</td></tr>
            <tr><td>log(x)</td><td>Natural logarithm ln(x)</td><td>Rate calculations</td></tr>
            <tr><td>log10(x)</td><td>Base-10 logarithm</td><td>Absorbance calculations</td></tr>
            <tr><td>log2(x)</td><td>Base-2 logarithm</td><td>Information/bit-depth calculations</td></tr>
            <tr><td>exp(x)</td><td>Exponential e^x</td><td>Inverse of ln</td></tr>
            <tr><td>sin(x), cos(x)</td><td>Trigonometric</td><td>Interferogram analysis</td></tr>
            <tr><td>mean_val(x)</td><td>Mean value (scalar) &mdash; use inside an
                expression, e.g. <code>sp1 - mean_val(sp1)</code></td><td>Mean-centring</td></tr>
            <tr><td>sum_val(x)</td><td>Sum (scalar) &mdash; use inside an expression</td><td>Total integrated signal</td></tr>
            <tr><td>min_val(x), max_val(x)</td><td>Minimum/maximum (scalar) &mdash; use inside an expression</td><td>Peak detection</td></tr>
            <tr><td>cumsum(x)</td><td>Cumulative sum (spectrum)</td><td>Integration</td></tr>
            <tr><td>absorbance(x)</td><td>A = &minus;log&#x2081;&#x2080;(T), with T clipped to a
                small positive floor to avoid log(0) or log(negative)</td><td>Transmittance &rarr; absorbance</td></tr>
            <tr><td>transmittance(x)</td><td>T = 10^(&minus;A) &mdash; exact inverse of absorbance()</td><td>Absorbance &rarr; transmittance</td></tr>
            <tr><td>kubelka_munk(x)</td><td>F(R) = (1&minus;R)&sup2; / (2R), with R clipped to
                (0, 1)</td><td>Diffuse reflectance analysis</td></tr>
            <tr><td>derivative(x)</td><td>First derivative, computed using the spectrum's
                real x-axis spacing</td><td>Overlapping band resolution</td></tr>
            <tr><td>second_deriv(x)</td><td>Second derivative, same real-spacing
                handling</td><td>Peak position identification</td></tr>
            <tr><td>normalise(x)</td><td>Min-max to [0, 1]</td><td>Comparison of band shapes</td></tr>
            <tr><td>snv(x)</td><td>Standard Normal Variate</td><td>Scatter correction</td></tr>
        </table>

        <div class="tip">
            <strong>Why absorbance, transmittance, and Kubelka-Munk "clip" instead of
            taking an absolute value:</strong> these three formulas all involve a
            logarithm or a division, and both blow up (or become undefined) at zero,
            and a logarithm of a negative number isn't a real number at all. A
            transmittance or reflectance value is only physically meaningful between 0
            and 1 anyway (0% to 100% of light), so tiny negative values or exact zeros
            in real data are measurement noise, not a real physical signal. "Clipping"
            means nudging any such tiny/negative noise up to a very small positive
            number (and capping values just under 1 the same way for Kubelka-Munk)
            before doing the math, so the result stays a normal, finite number instead
            of becoming NaN or infinity. Taking an absolute value instead — flipping a
            small negative reading to a small positive one — would technically avoid
            the same crash, but it quietly treats "probably zero, just noisy" the same
            as "twice that value but the wrong sign," which has no physical
            justification and can distort the result more than the noise already did.
            Clipping keeps the same fix in spirit (no more crashes) while staying
            closer to what the value should have meant.
        </div>

        <h3>Constants</h3>
        <table>
            <tr><th>Name</th><th>Value</th></tr>
            <tr><td>pi</td><td>3.14159&hellip;</td></tr>
            <tr><td>e</td><td>2.71828&hellip;</td></tr>
        </table>

        <h2>Formula Examples</h2>
        <p>The "Formula examples" section in the dialog (click any entry to insert it)
        is collapsed by default to leave more room for the Preview panel — click its
        header to expand or collapse it. The examples below mirror what's there:</p>

        <h3>Linear combination</h3>
        <div class="code">2 * sp1 + 0.5 * sp2 - sp3</div>
        <p>Weighted sum of multiple spectra. Useful for synthetic mixture spectra,
        component subtraction, or creating reference spectra.</p>

        <h3>Ratio spectrum</h3>
        <div class="code">sp1 / sp2</div>
        <p>Element-wise ratio. Common uses: reflectance (sample/reference),
        band-ratio indices, normalisation to an internal standard.</p>

        <h3>Normalised difference index</h3>
        <div class="code">(sp1 - sp2) / (sp1 + sp2)</div>
        <p>Results in values between &minus;1 and 1. Analogous to NDVI in remote
        sensing. Used to highlight relative differences between two spectral
        contributions while suppressing common components.</p>

        <h3>Transmittance to absorbance</h3>
        <div class="code">absorbance(sp1)</div>
        <p>Equivalent to &minus;log&#x2081;&#x2080;(T). Converts a transmittance spectrum
        to absorbance. Negative or zero values in sp1 are handled via absolute value
        to avoid NaN.</p>

        <h3>Absorbance to transmittance</h3>
        <div class="code">transmittance(sp1)</div>
        <p>Equivalent to 10^(&minus;A). Inverse of the absorbance conversion.</p>

        <h3>Kubelka-Munk transform</h3>
        <div class="code">kubelka_munk(sp1)</div>
        <p>F(R) = (1&minus;R)&sup2; / (2R). Standard transform for diffuse
        reflectance spectra; linearises the relationship between reflectance and
        concentration.</p>

        <h3>First derivative</h3>
        <div class="code">derivative(sp1)</div>
        <p>Resolves overlapping bands and removes baseline offsets. Apply
        Savitzky-Golay smoothing before differentiation for noisy spectra.</p>

        <h3>Second derivative</h3>
        <div class="code">second_deriv(sp1)</div>
        <p>Enhances peak positions and further resolves overlapping bands.
        Peaks appear as negative minima.</p>

        <h3>Standard Normal Variate (SNV)</h3>
        <div class="code">snv(sp1)</div>
        <p>Mean-centres and scales by standard deviation: (y &minus; mean) / std.
        Corrects for multiplicative scatter effects in diffuse reflectance
        spectroscopy.</p>

        <h3>Square root</h3>
        <div class="code">sqrt(abs(sp1))</div>
        <p>Compresses dynamic range. Useful before PCA or when signal spans
        many orders of magnitude.</p>

        <h3>Combining transforms</h3>
        <div class="code">derivative(snv(sp1))</div>
        <p>Transforms can be nested. Here: SNV followed by first derivative,
        a common preprocessing chain for NIR spectroscopy.</p>

        <h3>Mixing a spectrum with a constant</h3>
        <div class="code">sp1 - mean_val(sp1)</div>
        <p>Mean-centres a spectrum by subtracting its own mean value (a scalar).</p>

        <h3>Multiple outputs from one formula</h3>
        <div class="code">[sp1 - mean_val(sp1), sp2 - mean_val(sp2)]</div>
        <p>Wrapping several results in square brackets produces that many output
        spectra in a single run, instead of one combined result. Each must be the
        same length as the shared x-axis. Outputs are named automatically using the
        "New spectrum name" field as a base: a single output keeps the name as typed;
        multiple outputs are numbered <em>&lt;name&gt;_1</em>, <em>&lt;name&gt;_2</em>,
        and so on.</p>

        <h3>Spectral index</h3>
        <div class="code">(sp1 - 0.5 * sp2) / (sp1 + 0.5 * sp2)</div>
        <p>A weighted normalised difference index with an adjustable coefficient.</p>

        <h2>Output Options</h2>
        <ul>
            <li><strong>New spectrum name:</strong> the base label given to the result
                spectrum (or spectra) in the main list. For a formula producing several
                output spectra, this becomes the base for automatic numbering
                (see "Multiple outputs from one formula" above).</li>
            <li><strong>Add as new vs. Replace:</strong> use this dialog's own
                <strong>Apply</strong> button to replace the source spectra used in the
                formula with the result(s), or <strong>Add as New</strong> to keep the
                sources untouched and add the result(s) as new entries instead — the
                same Apply / Add as New choice used by every other operation
                (Normalization, Baseline correction, etc.), so the behaviour is
                consistent across the whole application. The dialog closes itself once
                Apply or Add as New succeeds, the same as those other operations —
                reopen the calculator from Configure if you want to keep working with
                the result(s).</li>
            <li><strong>Note on Apply / Replace:</strong> unlike most other operations,
                Spectral Calculator doesn't require a 1-to-1 relationship between
                sources and results — a formula can combine many source spectra into
                just one or two outputs (e.g. five spectra reduced to
                <span class="code" style="padding:1px 4px;">[sp1+sp2, sp1-sp2]</span>).
                Apply replaces <em>every</em> selected source with the result(s), even
                sources the formula never actually referenced. If that's not what you
                want, select only the spectra the formula actually uses before
                clicking Apply, or use Add as New instead.</li>
        </ul>

        <div class="warn">
            <strong>Name uniqueness:</strong> if a chosen name already exists in the
            spectrum list, a numeric suffix is added automatically
            (e.g. <em>Calculator_result_2</em>).
        </div>

        <h2>X-Axis Requirement</h2>
        <p>Every spectrum used in the formula must share an <em>identical</em> x-axis
        (same number of points, same values) — the calculator does not interpolate or
        otherwise reconcile mismatched x-axes for you.</p>
        <div class="warn">
            <strong>If x-axes don't match,</strong> validation fails with a message
            naming the two specific spectra that differ and how many points each has.
            Use <strong>Define Spectral Range</strong> with <em>Apply linearisation</em>
            to bring all spectra onto the same x-axis first, then return to the
            calculator.
        </div>

        <h2>Validation</h2>
        <p>The <strong>Preview</strong> panel updates automatically as you type
        (briefly debounced), showing the current result or any error inline — this
        is usually enough to catch problems before clicking Validate, Apply, or Add as New.</p>
        <p>Click <strong>Validate formula</strong> to explicitly check for:</p>
        <ul>
            <li>Syntax errors in the formula.</li>
            <li>Spectrum labels that do not match any selected spectrum.</li>
            <li>Mismatched x-axes between the spectra used.</li>
            <li>Division by zero or other numerical errors.</li>
            <li>Result shape mismatches (including for individual outputs, if the
                formula produces several).</li>
        </ul>
        <p>A green &#10003; confirms the formula is valid, and also reports how many
        output spectra it produces if more than one. A red &#10007; shows the error
        message. Apply and Add as New also validate automatically before committing.</p>

        <h2>Safety</h2>
        <p>A formula can only use plain arithmetic (<code>+ - * / ** %</code>), the
        selected spectrum aliases, and the specific functions listed in the reference
        panel. This is enforced by parsing the formula and evaluating only that
        exact set of allowed constructs — the formula is never handed to Python's
        general-purpose evaluator, and attribute access (anything using a
        <code>.</code>, e.g. <code>sp1.something</code>) is never permitted at all.
        There is no way for a formula to reach the file system, the network, or any
        Python functionality outside the functions listed here.</p>

        <h2>Troubleshooting</h2>

        <h3>Formula says &ldquo;No spectrum labels found&rdquo;</h3>
        <p>The formula must use the aliases shown in the right-hand panel (sp1, sp2,
        ...), not the real spectrum names directly — typing the real name (especially
        a long one) won't be recognised. Click an alias in the panel to insert it
        safely, or check the tooltip there to confirm which alias matches which
        spectrum.</p>

        <h3>Division by zero</h3>
        <p>Occurs when a denominator spectrum has zero values. Add a small constant to
        avoid it:</p>
        <div class="code">sp1 / (sp2 + 1e-10)</div>

        <h3>NaN or Inf in result</h3>
        <p>Log or square root of negative values produces NaN. Use abs() to guard:</p>
        <div class="code">log10(abs(sp1))</div>

        <h3>Spectra have different x-axes</h3>
        <p>The error message names the two specific spectra and their point counts.
        Use <strong>Define Spectral Range</strong> with <em>Apply linearisation</em> to
        bring all selected spectra onto an identical x-axis, then reopen the
        calculator.</p>

        <h3>Result looks wrong after Run</h3>
        <p>Click Validate formula to confirm the formula is correct, then check that
        the aliases used in the formula still point to the spectra you expect (hover
        over each entry in the right-hand panel to confirm). If the selection changed
        since Parameters was set, reopen Parameters — aliases are reassigned based on
        the current selection, so re-check the formula still says what you intend.</p>

        <h3>Only got one output spectrum, expected several</h3>
        <p>Multiple outputs require the formula's final result to be a Python list,
        e.g. <code>[sp1 - sp2, sp1 + sp2]</code>. A formula without the surrounding
        square brackets always produces exactly one output, however many spectra it
        combines internally.</p>

        <h3>"... is not allowed in a formula"</h3>
        <p>The formula uses a construct outside plain arithmetic, spectrum aliases,
        and the listed functions — most commonly a comparison
        (<code>sp1 &gt; 0</code>), a method or attribute access
        (<code>sp1.anything</code>), or a text/string value. Rewrite the formula
        using only <code>+ - * / ** %</code>, spectrum aliases, numbers, and the
        functions in the reference panel.</p>

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
