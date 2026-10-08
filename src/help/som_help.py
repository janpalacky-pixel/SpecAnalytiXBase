# src/help/som_help.py

def get_som_help_title():
    return "Self-Organizing Map (SOM) — Help"

def get_som_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1565C0; margin-top: 22px; }
            h3    { color: #E65100; margin-top: 14px; margin-bottom: 4px; }
            .note { background: #E3F2FD; border-left: 4px solid #1565C0;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .detail { background: #FFF3E0; border-left: 4px solid #E65100;
                    padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
            .fm   { font-family: monospace; background: #ececec;
                    padding: 1px 5px; border-radius: 3px; }
            table { border-collapse: collapse; width: 100%; margin: 8px 0; }
            th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
            td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
            ul,ol { padding-left: 20px; }
            li    { margin: 3px 0; }
        </style>
    </head>
    <body>

    <h1>Self-Organizing Map (SOM)</h1>

    <p>A Self-Organizing Map is an unsupervised neural network that trains a small
    grid of "nodes" to represent the overall shape of your spectra dataset. Each
    spectrum is assigned to the single node whose learned weight vector is closest
    to it (its <em>Best-Matching Unit</em>, or BMU). Spectra that are similar
    end up mapped to the same or neighbouring nodes, so the trained grid becomes a
    2D map of how your spectra relate to one another — similar to what Cluster
    Analysis or PCA show, but preserving neighbourhood/topology relationships
    that clustering discards.</p>

    <div class="note">
        <strong>Requirement:</strong> All selected spectra must share an identical
        x-axis (same wavenumber/wavelength points and range) — SOM stacks every
        selected spectrum into one matrix, exactly like Cluster Analysis, PCA,
        NMF, MCR-ALS, and SVD analysis. Use the <em>Data Range</em> step to
        harmonize spectra onto a common axis first if needed. This is required
        whichever Training Data mode you use below.
    </div>

    <h2 id="tryit">Try it yourself — bundled demo datasets</h2>
    <p>Two ready-made multi-class datasets ship with the app, reachable from
    <strong>Help &rarr; Test datasets &rarr; Synthetic &rarr; Self-Organizing
    Map (SOM)</strong> — pick one, it imports straight into the application:</p>
    <ul>
        <li><strong>SOM — Raman multi-class demo (240 spectra)</strong> —
            sharp fingerprint bands (400&ndash;1800&nbsp;cm<sup>-1</sup>), 5
            biomolecule-signature classes (protein, lipid, nucleic acid,
            carbohydrate, silica) plus a "Mixed/Reference" blend class.</li>
        <li><strong>SOM — UV/Vis multi-class demo (250 spectra)</strong> —
            broad, overlapping electronic bands (220&ndash;500&nbsp;nm), 4
            chromophore classes (aromatic, extended conjugation,
            charge-transfer, metal d-d) plus a "turbid/scattering" class.</li>
    </ul>
    <p>Each workbook's own <em>Info</em> sheet has the full story and a
    step-by-step walkthrough (suggested grid size, and specific Component
    Plane / Custom features settings to try), and its <em>Ground_truth</em>
    sheet lists the true class per spectrum so you can check the trained
    map's Hit Map / U-Matrix regions against what actually generated the
    data. Both were validated against this app's own SOM engine before
    shipping: on an 8&times;8 grid, every trained node comes out
    essentially single-class. See
    <a href="#verify">How to verify SOM is working correctly</a> at the end
    of this page for a step-by-step check against each dataset's known
    ground truth, with the exact numbers to expect.</p>

    <h2>Workflow</h2>
    <ol>
        <li>Select and preprocess spectra (baseline, normalization, smoothing).</li>
        <li>Choose <em>SOM</em> from the Visualization menu (or the Spectra
            Analysis &amp; Visualization groupbox) and it will open a dialog.</li>
        <li>Choose what to train on (Training Data) and set the grid size and
            training parameters.</li>
        <li>Click <strong>Run SOM</strong>.</li>
        <li>Inspect the map in different visualization modes.</li>
        <li>Click a node (or a row in the results table, or a point on the
            Sample Map) to see which spectra were assigned to it, and use
            <strong>Show Node Spectra</strong> to see their actual curves.</li>
        <li>Export results to Excel or CSV if needed.</li>
    </ol>

    <h2>Training Data — what the map learns from</h2>
    <p>Every orange "?" button in this dialog opens a short explanation of the
    controls next to it — this section covers the same ground in one place.</p>
    <table>
        <tr><th>Mode</th><th>Meaning</th></tr>
        <tr><td>Full spectrum shape<br>(default)</td><td>Each spectrum's complete
            curve is one training vector — the original behaviour. Two spectra
            end up on the same/neighbouring node when their overall shapes are
            similar.</td></tr>
        <tr><td>Custom features</td><td>Each spectrum is reduced to a short list
            of scalar numbers you define first (e.g. a peak position, a band
            integral, the intensity at one x-value), using the same engine as
            this app's standalone Band Ratio / Peak Area Calculator tool. The
            map organises spectra by those chosen numbers instead of by
            full-curve shape.</td></tr>
    </table>
    <div class="detail">
        <strong>Analogy to MeltAnalytiX:</strong> this is the SpecAnalytiXBase
        equivalent of MeltAnalytiX's own SOM dialog toggle between
        <em>clustering by extracted features</em> (Tm, van't Hoff enthalpy,
        hysteresis, ...) and <em>clustering by melting-curve shape</em>.
        MeltAnalytiX can name specific melting-curve features because it only
        ever handles melting curves; SpecAnalytiXBase is general-purpose
        (spectra here have no forced sample/condition/run grouping and no
        assumed curve type), so instead of a fixed feature list it lets you
        define your own Name / Metric / X1 / X2 rows.
    </div>

    <h2>Training Parameters</h2>
    <table>
        <tr><th>Parameter</th><th>Meaning</th></tr>
        <tr><td>Training method</td><td><strong>Online</strong> (classic, the default)
            adjusts the map after every single spectrum. It is the established
            method, but it can take minutes for hundreds of spectra.
            <strong>Batch</strong> finds the best node of all spectra at once in
            every pass and is typically <strong>10&ndash;50 times faster</strong>
            (seconds). It is a <em>different algorithm</em>, so the map is not
            identical to the online one, and it does not use the learning rates.</td></tr>
        <tr><td>Grid rows / cols</td><td>Size of the node grid (rectangular topology).
            More nodes give finer resolution but need more spectra and more
            iterations to train well. A common starting point is a grid with
            roughly <span class="fm">5 * sqrt(n_spectra)</span> total nodes.</td></tr>
        <tr><td>Learning rate start / end</td><td>Step size for weight updates.
            It decays geometrically from <em>start</em> down to <em>end</em> over
            training — large early updates organize the map's overall layout
            quickly, small late updates fine-tune it without destabilizing it.</td></tr>
        <tr><td>Neighborhood radius (end)</td><td>How many neighbouring nodes are
            still updated together late in training, in grid units. It starts at
            half the larger grid dimension and decays geometrically down to this
            value — early on, a whole neighbourhood moves toward each sample
            (organizing topology); late in training, only the winning node and its
            closest neighbours still move (refining local detail).</td></tr>
        <tr><td>Iterations (full passes)</td><td>Number of full passes over the
            (reshuffled) spectra. More passes converge to a more stable map, at
            the cost of longer training time. Training uses a fixed random seed,
            so the same settings always reproduce the same map exactly.</td></tr>
    </table>
    <div class="tip">
        <strong>Online or Batch?</strong> Measured on a map of 625 spectra
        (1800 points each) with a 10&times;10 grid: Online took 77&nbsp;s for the
        default 300 passes, Batch 1.5&nbsp;s. Batch gave about 1% higher
        quantization error and somewhat less perfect neighbourhood preservation
        (5&ndash;8% of spectra had their two best nodes not next to each other,
        against 0% for Online). For exploring, choose Batch; for a final map, run
        both and compare. While training, the progress window shows an estimate of
        the remaining time and a <strong>Cancel</strong> button. Cancelling stops
        training after the current pass and keeps the previous map (if there was
        one) exactly as it was.
    </div>

    <h3>How Online and Batch training differ</h3>
    <p>Both start from the same initial map (nodes spread along the two main
    directions of variation in your data) and shrink the neighbourhood radius in the
    same way. They differ in how the nodes are moved:</p>
    <ul>
        <li><strong>Online (classic)</strong> takes one spectrum at a time (in random
        order), finds its best node, and pulls that node and its grid neighbours a
        little toward the spectrum &mdash; then the next spectrum, and so on. With 625
        spectra and 300 passes that is 187,500 small steps, each depending on the one
        before, so it cannot be sped up by using more processor cores.</li>
        <li><strong>Batch</strong> first finds the best node of <em>every</em> spectrum
        with the map as it is, then moves each node in one step to the average of the
        spectra assigned to it and to its neighbours (closer neighbours count more).
        One pass is a few matrix operations, which is why it is so much faster. It has
        no learning rate.</li>
    </ul>

    <h3>Measuring map quality</h3>
    <ul>
        <li><strong>Quantization error</strong> &mdash; the average distance between each
        spectrum and its best node. It says how well the nodes <em>represent</em> the
        spectra: smaller is better. Batch is typically about 1% higher than Online.</li>
        <li><strong>Topographic error</strong> &mdash; the fraction of spectra whose best
        and second-best nodes are <em>not</em> neighbours on the grid. It says how well
        the map keeps <em>similar spectra next to each other</em> (the whole point of a
        SOM compared with plain clustering): 0% is perfect. Online reached 0% on the test
        data, Batch 5&ndash;8%, i.e. for a few spectra the second-best node lies
        further away on the map.</li>
    </ul>

    <div class="note">
        <strong>Rotated or mirrored maps are normal.</strong> A SOM has no fixed
        &ldquo;up&rdquo; or &ldquo;left&rdquo;: a map turned by 90&deg;/180&deg; or
        mirrored describes exactly the same relationships between your spectra. Online
        and Batch often end up in different orientations of the same structure, so
        compare <em>which spectra share or neighbour a node</em>, not where on the grid
        they sit.
    </div>
    <div class="detail">
        <strong>Why aren't these adjustable in MeltAnalytiX?</strong> They exist
        in MeltAnalytiX's own SOM training engine too — this dialog's algorithm
        is ported directly from it — but MeltAnalytiX's dialog only exposes
        Grid rows/cols as controls and leaves learning rate, radius, and
        iterations at the engine's built-in defaults. SpecAnalytiXBase's dialog
        surfaces the full set.
    </div>

    <h2>Visualization modes</h2>
    <ul>
        <li><strong>U-Matrix</strong> — the mean distance between each node and
            its immediate neighbours. Light regions are internally similar
            areas of the map ("clusters"); dark ridges mark boundaries between
            groups of dissimilar spectra.</li>
        <li><strong>Hit Map</strong> — how many spectra were assigned to each
            node. Useful for spotting under-used regions of an over-sized grid,
            or a few nodes absorbing most of the dataset.</li>
        <li><strong>Component Plane</strong> — one trained value per node across
            the grid. In <em>Full spectrum shape</em> mode you can choose what
            that value is: the raw trained weight at one wavelength index (the
            original behaviour), the node's reconstructed prototype spectrum's
            intensity at one x-value, a Band-Ratio-style metric (Mean, Integral,
            Baseline-corrected integral, Variance, Peak intensity, Peak
            position) over an x-range, or the ratio/difference/sum of that
            metric between two separate x-ranges. A single x-value can be
            sensitive to noise, so the range-based metrics are usually the more
            robust choice. In <em>Custom features</em> mode, each Component
            Plane already corresponds to one of your defined features, so the
            picker is replaced by a simple feature-name dropdown.</li>
        <li><strong>Sample Map</strong> — every individual spectrum plotted as
            one point inside its own best-matching node's grid cell (spread out
            with a small jitter so same-node points don't overlap), optionally
            coloured by distance-to-BMU or, in <em>Custom features</em> mode, by
            any one of your defined features. Click a point to select its node,
            same as clicking a cell in the other modes.</li>
    </ul>
    <div class="note">
        Nodes with zero assigned spectra are drawn with a diagonal hatch
        pattern in every visualization mode, so an "empty" cell is never
        mistaken for a real, low value.
    </div>

    <div class="tip">
        <strong>Tip:</strong> switching between visualization modes, or changing
        Component Plane / Sample Map display settings, is instant — it only
        redraws the already-trained map, it does not retrain. Changing a
        Training Data or Training Parameters setting marks the results stale;
        click <strong>Run SOM</strong> again to retrain with the new settings.
    </div>

    <h2>Node spectra</h2>
    <p>Selecting a node (by clicking it, a results-table row, or a Sample Map
    point) shows its member spectra labels in the Node Information panel.
    Click <strong>Show Node Spectra</strong> there to open a plot of the
    actual overlaid curves for those spectra — not just their names — plus,
    in <em>Full spectrum shape</em> mode, the node's own reconstructed
    prototype spectrum as a bold reference curve.</p>

    <h2>Relationship to spectra</h2>
    <p>Like Cluster Analysis, PCA Scores &amp; Loadings, NMF, MCR-ALS, and SVD
    analysis, SOM is a read-only visualization/analysis tool: it never modifies,
    adds, or deletes any spectrum in the main list. Results exist only inside
    this dialog and in whatever you explicitly export.</p>

    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default regardless
    of the main window's setting. When checked, it applies to the member-spectra
    list shown in the Node Information panel (and to the legend in the Node
    Spectra plot), and updates immediately if a node is already selected. It
    only affects what is <em>displayed</em> — spectrum identity, and any name
    written into an exported file, is always the full original label.</p>

    <h2 id="verify">How to verify SOM is working correctly</h2>
    <p>Both bundled demo datasets (see
    <a href="#tryit">Try it yourself</a> above) ship with a known ground
    truth &mdash; a <em>Ground_truth</em> sheet listing the true class (and
    a continuous "purity"/blend value) behind every spectrum, entirely
    independent of anything SOM computes. That makes them a genuine
    correctness check, not just a pretty picture: if the trained map's
    regions line up with the true classes, the algorithm is doing its job.
    The numbers below are exactly what this app's own SOM engine produced
    on both files at the settings described (grid 8&times;8, 300
    iterations, default learning rate/radius/seed) &mdash; use them as the
    target to compare your own run against.</p>

    <h3>1. Run both datasets</h3>
    <ol>
        <li>File &rarr; Import data &rarr; open
            <span class="fm">som_raman_multiclass_demo.xlsx</span> (or use
            <strong>Help &rarr; Test datasets &rarr; Synthetic &rarr;
            Self-Organizing Map (SOM)</strong>), then select all 240
            imported spectra.</li>
        <li>Open <em>Visualization &amp; Analysis &rarr; SOM</em>. Leave
            Training Data on <em>Full spectrum shape</em>, set Grid rows
            and cols to <strong>8</strong>, Iterations to
            <strong>300</strong>, leave the learning rate/radius at their
            defaults, and click <strong>Run SOM</strong>.</li>
        <li>Repeat with <span class="fm">som_uvvis_multiclass_demo.xlsx</span>
            (250 spectra, same 8&times;8 / 300-iteration settings).</li>
    </ol>
    <div class="detail">
        <strong>Why 8&times;8 and not a smaller grid matching the class
        count?</strong> The Raman set has 6 true classes (5 pure + Mixed/
        Reference) and the UV/Vis set has 5 (4 pure + turbid), so "one node
        per class" (a 2&times;3 or 3&times;3 grid) sounds like a reasonable
        idea &mdash; but tested against these files it backfires badly on
        one of them:
        <table>
            <tr><th>Grid</th><th>Raman &mdash; mean node purity</th><th>UV/Vis &mdash; mean node purity</th></tr>
            <tr><td>2&times;3 (6 nodes)</td><td>49%</td><td>100%</td></tr>
            <tr><td>3&times;3 (9 nodes)</td><td>60%</td><td>100%</td></tr>
            <tr><td>4&times;4 (16 nodes)</td><td>86%</td><td>100%</td></tr>
            <tr><td>6&times;6 (36 nodes)</td><td>96%</td><td>100%</td></tr>
            <tr><td>8&times;8 (64 nodes)</td><td>99%</td><td>100%</td></tr>
        </table>
        UV/Vis barely cares &mdash; its classes are broad and cleanly
        separated, so even 5 nodes for 5 classes nails a perfect split.
        Raman cares a great deal: its classes were deliberately built with
        overlapping structure (the purity blending described above, which
        is realistic &mdash; real biological samples rarely have crisp,
        non-overlapping signatures), and a too-small grid has no choice but
        to average that overlap into a handful of coarse prototypes,
        crushing genuinely different classes together. More nodes than
        classes lets the map spread that overlap out smoothly instead.
        Since you don't generally know in advance how separable your own
        classes are, erring toward more nodes (this page's earlier
        <span class="fm">5&nbsp;*&nbsp;sqrt(n_spectra)</span> rule of thumb)
        is the safer default &mdash; which is exactly why the walkthrough
        above uses it rather than a grid sized to the known class count.
    </div>

    <h3>2. Eyeball the region count</h3>
    <p>On the U-Matrix (dark ridges = boundaries) and Hit Map, you should
    see roughly as many separated regions as there are true classes: about
    5&ndash;6 for the Raman set (5 biomolecule classes, with Mixed/
    Reference straddling their boundaries rather than forming a clean 6th
    island), and about 4&ndash;5 for the UV/Vis set (4 chromophore classes
    plus a separate turbid region). If instead you see one giant blob or as
    many regions as spectra, that points to a training problem (grid too
    small/large, too few iterations, or spectra that weren't actually
    comparable) rather than a correctly organised map.</p>

    <h3>3. Check node purity against the Ground_truth sheet</h3>
    <p><strong>Fastest check &mdash; right in the app, no spreadsheet
    needed:</strong> every spectrum's label already encodes its true class
    (e.g. <span class="fm">protein_012_p87</span> = class "protein", 87%
    purity). Click any node in the Hit Map or U-Matrix (or a row in the
    results table) &mdash; the <em>Node Information</em> panel below the
    canvas lists the labels of every spectrum assigned to it. On a
    correctly trained map, the labels for one node should mostly (often
    all) start with the same class word. Click through several nodes
    scattered around the map and check the same thing each time; that
    alone is a real, if informal, correctness check.</p>
    <p><strong>One summary number for the whole map &mdash; step by
    step:</strong></p>
    <ol>
        <li>In the SOM dialog: <strong>Export CSV &rarr; Export BMU
            Assignments (detailed)</strong>, save it as e.g.
            <span class="fm">assignments.csv</span>.</li>
        <li>Open <span class="fm">assignments.csv</span> in Excel &mdash;
            it has 3 columns: Spectrum, Node_Row, Node_Col.</li>
        <li>Also open the demo workbook (e.g.
            <span class="fm">som_raman_multiclass_demo.xlsx</span>).
            Right-click its <em>Ground_truth</em> tab at the bottom
            &rarr; <em>Move or Copy...</em> &rarr; under "To book" choose
            your assignments.csv file &rarr; tick <em>Create a copy</em>
            &rarr; OK. Your assignments file now has a Ground_truth tab
            too.</li>
        <li>Back on the assignments sheet, label cell D1
            <span class="fm">True_class</span>, and in D2 type
            <span class="fm">=VLOOKUP(A2,Ground_truth!A:B,2,FALSE)</span>,
            then fill that formula down to the last row.</li>
        <li>Label cell E1 <span class="fm">Node</span>, and in E2 type
            <span class="fm">=B2&amp;"-"&amp;C2</span>, then fill down
            &mdash; this glues each spectrum's Node_Row and Node_Col into
            one label per node (e.g. "3-7").</li>
        <li>Select the data and sort it (<em>Data &rarr; Sort</em>) by
            column E (Node) first, then by column D (True_class) as a
            second key. Now scroll down column D: within each block of
            matching Node values you should see mostly (ideally only) one
            class repeated. A node whose block shows a mix of different
            classes is a "mixed" node &mdash; a handful of these is normal,
            just not the norm across the whole map.</li>
        <li><em>Optional, for one overall percentage:</em> if you're
            comfortable with pivot tables, <em>Insert &rarr;
            PivotTable</em> with Rows = Node, Columns = True_class, Values
            = Count of Spectrum &mdash; a row that lands entirely in one
            column is a 100%-pure node.</li>
    </ol>
    <div class="note">
        <strong>The occupied-node count is not the number to check.</strong>
        Exactly how many of the 64 grid cells end up occupied (and exactly
        how many spectra land in each) shifts by a few nodes between runs
        even at identical Grid rows/cols and Iterations &mdash; the random
        seed, the exact iteration count, any preprocessing you applied
        before running SOM, and even the order spectra happen to be
        selected in all nudge the training path slightly, and a stochastic,
        sequential algorithm like this one is expected to settle into a
        slightly different final layout each time. <strong>Mean node
        purity is the number that stays stable</strong> &mdash; that's what
        to compare against the figures below, not the exact node count.
    </div>
    <p>Repeating the run above at several different iteration counts and
    random seeds (grid always 8&times;8, unprocessed data), this app's own
    engine gave:</p>
    <table>
        <tr><th>Dataset</th><th>Occupied nodes (varies by run)</th><th>Mean node purity (stable)</th></tr>
        <tr><td>Raman multi-class demo</td><td>47&ndash;50 of 64</td><td>&asymp; 99.3&ndash;99.4% every time</td></tr>
        <tr><td>UV/Vis multi-class demo</td><td>45&ndash;47 of 64</td><td>100% every time</td></tr>
    </table>
    <p>A run whose mean purity lands in that range demonstrates the map is
    genuinely separating the classes, not just producing a plausible-looking
    picture &mdash; whatever the exact occupied-node count happens to be.</p>

    <h3>4. Confirm the "blend class" story &mdash; the topology check</h3>
    <p>This is the check that specifically demonstrates SOM's topology
    preservation, not just clustering: click through the nodes bordering
    the Raman set's Mixed/Reference-majority nodes and confirm their
    majority class varies rather than repeating. Repeating this app's own
    validation run across several iteration counts and random seeds, the
    Mixed/Reference nodes consistently bordered <strong>4 of the 5</strong>
    pure classes (protein, lipid, nucleic acid, silica) every single time
    &mdash; i.e. Mixed/Reference reliably sits <em>between</em> several
    regions rather than off on its own, exactly as expected from a random
    blend of every class's bands.</p>
    <p>The UV/Vis set is a deliberate contrast: its "turbid" class is
    defined by the <em>absence</em> of a strong band (a scattering
    baseline), not a blend, so it should instead form its own, mostly
    separate region. Across the same repeated validation, turbid usually
    bordered <strong>0</strong> of the other 4 chromophore classes, and
    occasionally just 1 &mdash; markedly less than Mixed/Reference's
    consistent 4, and never once did it behave like Mixed/Reference and
    touch most of the others. Seeing this contrast between the two files
    &mdash; one "extra" class reliably sitting in the middle, the other
    reliably sitting mostly apart &mdash; is itself evidence the map
    reflects real structure in the data rather than an artifact of these
    two files happening to look similar.</p>

    <h3>5. Confirm the purity gradient</h3>
    <p>Switch Visualization to <strong>Sample Map</strong>, Color by:
    <em>Distance to BMU</em>. Within any one class, the lowest-purity
    samples (the smallest p-number in the label, e.g.
    <span class="fm">..._p058</span>) should tend to sit further from their
    node's prototype (a brighter colour) and closer to the Mixed/Reference
    (or turbid) boundary than the highest-purity samples of the same class
    &mdash; because that is literally how they were constructed. This is
    the kind of within-class structure ordinary hard clustering discards
    but a SOM's neighbourhood-preserving training keeps visible.</p>

    <h3>6. Cross-check with the newer dialog features</h3>
    <p>Two more independent checks, exercising the Component Plane and
    Custom features additions:</p>
    <ul>
        <li><strong>Component Plane &rarr; Ratio of two ranges (A/B).</strong>
            Raman: Band metric <em>Mean</em>, Band A X1/X2 =
            1630/1680 (protein Amide I), Band B X1/X2 = 1420/1460 (lipid
            CH2 bending). UV/Vis: Band A X1/X2 = 390/410
            (charge-transfer), Band B X1/X2 = 268/288 (aromatic). The
            resulting plane should read high specifically over that
            class's own map region.</li>
        <li><strong>Training Data &rarr; Custom features.</strong> Add the
            three rows suggested in each workbook's Info sheet, re-run, and
            confirm the map still separates the classes about as well on
            this much smaller, hand-picked feature representation. Because
            this uses a completely different training input (3 numbers
            instead of hundreds of raw intensities) landing on the same
            class structure is strong independent evidence the separation
            reflects the real data, not an artifact of full-spectrum
            Euclidean distance specifically.</li>
    </ul>

    <div class="tip">
        <strong>In short:</strong> a correctly working SOM on these two
        files should (1) show roughly the right number of regions, (2) put
        the great majority of each node's members in one true class, (3)
        place the "extra" class exactly where its construction predicts
        &mdash; between the others for a blend, apart from them for an
        absence &mdash; and (4) reproduce that structure again under a
        completely different training representation (Custom features).
        Any one of these on its own could be a coincidence; all four
        together is a genuine correctness demonstration.
    </div>

    </body>
    </html>
    """
