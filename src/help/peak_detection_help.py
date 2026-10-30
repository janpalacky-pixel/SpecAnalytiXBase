# src/help/peak_detection_help.py

def get_peak_detection_help_title():
    return "Peaks (Detect Peaks and the Peak list) — Help"

def get_peak_detection_help_content():
    from src.help.help_figures import figure_html
    page = _PAGE
    for key in ('PEAK_DIALOG', 'PEAK_LABELS', 'PEAK_NOISE', 'PEAK_MOVING', 'PEAK_BAND_TABLE'):
        page = page.replace(f'@@{key}@@', figure_html(key))
    return page


_PAGE = """
    <html><head><style>
        body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; font-size: 13px; }
        h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
        h2    { color: #1565C0; margin-top: 22px; }
        .tip  { background: #E8F5E9; border-left: 4px solid #2E7D32; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        .note { background: #E3F2FD; border-left: 4px solid #1565C0; padding: 10px 14px; border-radius: 3px; margin: 8px 0; }
        table { border-collapse: collapse; width: 100%; margin: 8px 0; }
        th    { background: #E3F2FD; text-align: left; padding: 6px 8px; }
        td    { border-bottom: 1px solid #e0e0e0; padding: 5px 8px; vertical-align: top; }
        ul,ol { padding-left: 20px; } li { margin: 3px 0; }
        hr    { border: none; border-top: 1px solid #ddd; margin: 20px 0; }
        .fm   { font-family: monospace; background: #ececec; padding: 1px 5px; border-radius: 3px; }
    </style></head><body>

    <h1>Peaks (Detect Peaks and the Peak list)</h1>

    <p>The <b>Peaks</b> window finds the local maxima or minima of the selected spectra and shows
    them in four tabs. It does not change your spectra or save anything to their metadata.
    <b>Right-click on the plot &rarr; Detect Peaks</b> opens it on the tab <b>Mark on the
    plot</b>, <b>Peak list&hellip;</b> on the tab <b>List</b> &mdash; it is one window:</p>
    <ul>
        <li>The <b>settings at the top</b> (Threshold, Prominence, Distance, S/N, Peaks) decide
            which peaks are found, the same for every tab.</li>
        <li><a href="#peak-list"><b>List</b></a>: every peak in a table, for Excel.</li>
        <li><a href="#peak-plot"><b>Plot</b></a>: one number of the peaks against another, e.g.
            the position against the temperature.</li>
        <li><a href="#band-table"><b>Band table</b></a>: one row per spectrum, one column per
            band &mdash; also <i>Open in the Data table</i>.</li>
        <li><a href="#mark"><b>Mark on the plot</b></a>: a red dot on every peak of the main plot
            and its position written next to it.</li>
    </ul>
    <p><b>Reset to defaults</b> puts every setting back to its default value. The orange
    <b>?</b> shows what each setting and column means; the same text appears when you hold the
    mouse over a setting.</p>

    <h2 id="how-to">How to use it, in short</h2>
    <ol>
        <li>Select the spectra so that they are plotted.</li>
        <li><b>Right-click on the plot &rarr; Detect Peaks &rarr; Mark the peaks on the plot.</b>
            The defaults suit most data: every peak that stands out clearly from its surroundings
            and from the noise is marked with a red dot. The window stays open: change a setting
            and the marks follow at once.</li>
        <li>With many similar spectra, each band's position is written <b>once</b>, above its
            highest peak (<i>Labels: once per band</i>). A range such as
            <code>247.19&ndash;256.18</code> means the peak <b>moves</b> through the series &mdash;
            see <a href="#good-to-know">Good to know</a>.</li>
        <li>A clear peak is missing? Lower <b>Prominence</b> (a small band next to a big one) or
            <b>Signal-to-noise</b> (a very weak band). Noise is marked? Raise
            <b>Signal-to-noise</b>. One broad band gives two dots? Raise <b>Distance</b>. Only the
            tall peaks wanted? Raise <b>Threshold</b>.</li>
        <li>The numbers of all peaks for Excel: the tab <b>List</b> or <b>Band table</b> of the
            same window (below). A precise position, width or area: tick <b>Refine by fitting</b>,
            or use Peak Fitting for overlapping bands.</li>
    </ol>
    @@PEAK_DIALOG@@
    @@PEAK_LABELS@@

    <div class="note">
        This is different from <strong>Peak Fitting</strong>, which models
        peaks mathematically (Gaussian/Lorentzian) and can save fitted
        parameters to a spectrum's metadata. Use Peak Detection for a quick
        visual survey of a plot; use Peak Fitting when you need quantitative
        peak parameters (center, height, FWHM, area).
    </div>

    <hr>
    <h2>Parameters</h2>
    <table>
        <tr><th>Parameter</th><th>Meaning</th></tr>
        <tr><td><strong>Threshold</strong></td>
            <td>Minimum height, as a fraction (0&ndash;1) of each line's own
            intensity range, a point must reach before it's even considered
            as a candidate peak. The default <b>0</b> sets no height limit: a peak
            is then judged only <i>locally</i>, by its prominence, so a small but
            clear band next to a strong one is found too. Raise it (e.g. 0.5 =
            only the upper half of the range) to keep only the tall peaks.</td></tr>
        <tr><td><strong>Prominence</strong></td>
            <td>How much a candidate peak must stand out from its
            surrounding baseline, as a fraction of the line's intensity
            range. Raise this to ignore small bumps riding on a larger
            feature.</td></tr>
        <tr><td><strong>Distance</strong></td>
            <td>Minimum spacing between detected peaks, as a fraction of the
            number of points in the line. Raise this to avoid multiple
            markers crowding around what's really one broad peak.</td></tr>
        <tr><td><strong>S/N</strong> (signal-to-noise, minimum)</td>
            <td>A peak must also stand out (its prominence) at least this many times
            the <b>noise</b> of its spectrum. The noise is estimated from each spectrum itself,
            from its point-to-point scatter, which the bands hardly affect. Prominence alone is a
            fraction of a spectrum's own range, so in a series the <i>weakest</i> spectra (whose
            range is not much bigger than their noise) gave many peaks that were only noise. Noise
            alone makes bumps up to about 6&ndash;7 times its standard deviation, so with the
            default <b>8</b> they are gone (e.g. a noisy CD series, Peaks: Both: at most 3 peaks
            per spectrum instead of 17). Lower it for very weak bands; <b>0</b> switches it off.
            Clean, smooth spectra are not affected.</td></tr>
        <tr><td><strong>Peaks</strong></td>
            <td><em>Positive</em> finds local maxima (upward peaks),
            <em>Negative</em> finds local minima (downward dips/troughs),
            <em>Both</em> finds both at once.</td></tr>
        <tr><td><strong>Labels</strong> (tab Mark on the plot)</td>
            <td>Which peaks get their position written. <em>Once per band</em> (the
            default): one number per band, above its highest peak &mdash; the peaks of all
            plotted spectra at about the same position (within half of their typical FWHM, as
            &ldquo;same band within &plusmn;&rdquo; in the <a href="#peak-list">Peak list</a>) are
            one band, and the number is the band's position (the median of its peaks). So eleven
            similar spectra show 7 numbers, not 70. A band whose peaks <i>move</i> through the
            series (spread over more than a quarter of the typical peak width) is written as its
            range, e.g. <code>247.19&ndash;256.18</code>: in CD, an extremum of overlapping
            positive and negative bands often shifts when the mixture changes, and one number
            would hide that. <em>On every peak</em>: each peak its own
            number. <em>Only the current spectrum</em>: the peaks of the spectrum highlighted in
            the spectra list. <em>None</em>: no numbers. The red dots mark every peak in all
            cases.</td></tr>
        <tr><td><strong>Font size / Text rotation / Decimal places / Number format / Display
            format</strong> (tab Mark on the plot)</td>
            <td>Purely cosmetic — control how (and whether) each marker's
            coordinates are labeled on the plot.</td></tr>
    </table>
    <p>Defaults: threshold 0, prominence 0.1, distance 0.05, signal-to-noise 8, Positive; labels once per band; font size 10,
    rotation 0, 2 decimal places, fixed point, x value only.</p>

    <hr>
    <h2>How detection works</h2>
    <p>Each plotted line is analyzed independently. For <em>Negative</em>
    mode, the line's y-values are inverted first, then searched the same
    way <em>Positive</em> mode searches the original — so a "negative peak"
    is really a local minimum (a downward-pointing dip) in your data.</p>
    <p>Threshold, Prominence and Distance are fractions of each line's own data — a
    threshold of 0.5, for instance, always means "half of this particular
    line's own range," not a fixed absolute value — so the same settings
    can be reused sensibly across lines with very different intensity
    scales. The <b>signal-to-noise</b> limit is the exception that makes this safe for weak
    lines: the noise of each line is estimated from the line itself (from the scatter of
    neighbouring points, which the bands hardly affect), and a peak must stand out at least
    8&times; that noise. Lines of fewer than 50 points have no noise limit (the bands would
    be mistaken for noise).</p>

    <hr>
    <h2 id="good-to-know">Good to know: what the peaks tell you, and what they do not</h2>
    <ul>
        <li><b>Peaks are judged locally.</b> A peak counts when it stands out from the valleys
            around it (Prominence) and from the noise (Signal-to-noise) &mdash; not when it is
            tall compared with the tallest peak of the spectrum. That is why Threshold is 0 by
            default: with 0.5, a small but clear band next to a strong one was missed (the band at
            344 in the picture above).</li>
        <li><b>Weak spectra and noise.</b> In a series, the weakest spectra have a range not much
            bigger than their noise; without the signal-to-noise limit their noise is taken for
            peaks. Noise alone makes bumps up to about 6&ndash;7&times; its standard deviation, so
            the default 8 keeps them out. Lower it only for very weak bands you trust.
            @@PEAK_NOISE@@</li>
        <li><b>A peak position is not always a band position.</b> Where bands overlap &mdash;
            above all in CD, where positive and negative bands partly cancel &mdash; the top or
            bottom of the sum lies between the bands and <b>moves when the mixture changes</b>,
            although no band moves. Detect Peaks then writes the range of positions. The tops and
            bottoms are fine for a quick look; for quantitative work use the signal at a fixed
            wavelength (e.g. 222&nbsp;nm in <a href="help://melting_curve">Melting Curve
            Analysis</a>, or a value in the Data table), band positions from
            <a href="help://peak_fitting">Peak Fitting</a> with several bands, or the components
            from <a href="help://mcr_als">MCR-ALS</a> or SVD.
            @@PEAK_MOVING@@</li>
        <li><b>Shoulders are not peaks.</b> A band on the side of a stronger one has no top of
            its own, so no setting finds it; Peak Fitting fits it together with its neighbour.</li>
        <li><b>The measured FWHM is too wide where bands overlap</b>, because it is read from the
            points and includes the neighbours. <b>Refine by fitting</b> fits a model band to each
            peak: choose the <b>shape</b> with the best R&sup2; (Gaussian for broad bands; a
            Lorentzian fitted to Gaussian bands gives widths about 10&nbsp;% too large; Pseudo-Voigt
            can become either). In a test with known Gaussian bands of FWHM 50.3: measured 53.6,
            Gaussian fit 50.6, Lorentzian fit 55.2.</li>
        <li><b>CD: use Peaks: Both.</b> Maxima and minima are each judged on their own range, so
            a small positive band is found next to a big negative one.</li>
        <li><b>A point where all spectra cross is not always an isodichroic (isosbestic)
            point.</b> If all spectra are near zero there (e.g. where a band changes sign), it
            holds for any mixture and says nothing about two states; a real isosbestic or
            isodichroic point also needs the total amount to stay constant. See
            <a href="help://isosbestic_point">Isosbestic / Isodichroic Point Detection</a>.</li>
    </ul>

    <hr>
    <h2 id="peak-list">Tab List</h2>
    <p>The tab <b>List</b> (right-click on the plot &rarr; <b>Peak list&hellip;</b> opens the window
    on it) lists every peak of <b>all selected spectra</b> in one table &mdash; also of spectra a
    large selection does not draw. The peaks are found by exactly the same rule and settings as
    the marks on the plot; change a setting at the top and the table follows at once.
    Columns:</p>
    <ul>
        <li><b>Peak</b>: its number within the spectrum, from low to high x; <b>Kind</b>: maximum
            or minimum.</li>
        <li><b>Position (x)</b> and <b>Height (y)</b>: of the highest (or lowest) measured point
            &mdash; so the position is as precise as the point spacing. For a position between the
            points, tick <b>Refine by fitting</b> (below).</li>
        <li><b>Prominence</b>: how far the peak stands out from its surroundings.</li>
        <li><b>FWHM</b>: the width at half of the prominence, and where it starts and ends
            (<b>Left / Right half-height x</b>), interpolated between the points (also for uneven
            point spacing). Overlapping bands make it a rough estimate.</li>
    </ul>
    <p><b>Double-click a peak</b> to see it on the main plot: its spectrum is highlighted (a wide
    pale band under its line) and the peak is circled, with the spectrum's name and the position
    &mdash; also in a stacked plot. The view does not change. The next double-click, <i>Clear
    Peaks</i> (right-click on the plot) or a new plot removes it. A spectrum that a large
    selection does not draw cannot be shown; the line under the settings then says so.</p>
    <p>Click a heading to sort by it. Select rows and press Ctrl+C (or <b>Copy</b>) to paste them
    into Excel with the column names; <b>Export&hellip;</b> saves the list as Excel or CSV.
    The orange <b>?</b> also explains the columns.</p>
    <h3 id="refine-by-fitting">Refine by fitting</h3>
    <p>Finding a peak and measuring it are two different jobs. The list <i>finds</i> the peaks from
    the measured points, so its position and height are those of one measured point and the
    width is read between the neighbouring valleys. Tick <b>Refine by fitting</b> to also
    <i>measure</i> every found peak precisely: a model band (<b>shape</b>: Gaussian, Lorentzian or
    Pseudo-Voigt) plus a <b>background</b> (Linear, Constant or None) is fitted by least squares
    to the points around the peak &mdash; &plusmn; 1.5 &times; its FWHM, at least 5 points on each
    side, but never beyond halfway to the next peak, so a neighbour is not fitted instead. It is
    the same fit as the <a href="help://map2d#peak-fit">peak-fit maps of the 2D map</a>. Five
    columns are added:</p>
    <ul>
        <li><b>Fitted position</b>: the centre of the fitted band &mdash; it can lie between the
            measured points, so shifts smaller than the point spacing become visible.</li>
        <li><b>Fitted FWHM</b>, <b>Fitted height</b> (above the fitted background) and
            <b>Fitted area</b> (the band's own area, without the background &mdash; usually the
            best measure of the amount).</li>
        <li><b>R&sup2;</b>: how well the model describes the points (1 = perfectly).</li>
    </ul>
    <p>A peak whose fit is rejected (e.g. two overlapping bands in its window, or too few points)
    gets empty cells; the line next to the settings says how many. The fitted columns are copied,
    exported and offered in the tab Plot and the Band table too. When you tick Refine by fitting,
    the Plot and the Band table switch to the fitted value at once (Position (x) &rarr; Fitted
    position, Height (y) &rarr; Fitted height, FWHM &rarr; Fitted FWHM), and back when you untick
    it. Long lists are fitted on several processor cores,
    with a progress bar and Cancel. For several overlapping peaks of one spectrum fitted together,
    use the Peak Fitting tool.</p>
    <p><b>Show on the main plot</b> (next to the fit settings) draws each fitted peak &mdash; the
    model band plus its background over the points it was fitted to &mdash; as a dashed black line
    over its spectrum on the main plot (also in a Waterfall plot), so you can see at once
    whether a fit describes the band. It draws the peaks of the selected rows of the table, or all
    peaks when no row is selected (at most 300 at once); select a few rows to check them one by one.
    The view of the plot does not change. Untick it, use <i>Clear Peaks</i> (right-click on the
    plot) or draw a new plot to remove them.</p>
    <h3 id="peak-plot">Tab Plot</h3>
    <p>The tab <b>Plot</b> draws one number of the peaks against another:</p>
    <ul>
        <li><b>x</b>: a value of the spectrum &mdash; its order in the list, a value stored with it
            (e.g. <code>temperature_C</code> of a JASCO temperature scan) or a number in its name
            (only values that differ between the spectra are offered) &mdash; or a number of the peak itself: position, height, prominence, FWHM or the
            peak number (1st, 2nd, &hellip; peak of its spectrum; e.g. the position against the peak
            number shows how much the 1st, 2nd, &hellip; peak varies between the spectra);</li>
        <li><b>x = Peak by its position</b>: each peak at the position of its band &mdash; peaks
            of different spectra closer than <b>same band within &plusmn;</b> (in x units; set from
            the widths of the peaks, half of the median FWHM) are the same band and get one common
            position (their median), so a band measured at 685 in one spectrum and 686 in the next
            is one column. <b>As labels</b> puts the bands side by side with their positions as
            names (e.g. 686, 1093); <b>on the x scale</b> puts them at their positions. A peak
            that is missing in some spectra (not found there) is not invented: its band simply has
            no point for those spectra, and the other bands keep their place &mdash; unlike the
            peak number, where the peaks after a missing one move up by one (the 2nd becomes the
            1st, &hellip;). A band that shifts gradually through a series stays one band as long
            as its neighbouring positions are within the &plusmn; distance; two bands closer than it
            become one (then lower it). Unlike <b>Position (x)</b>, all spectra share the band's
            position;</li>
        <li><b>y</b>: position, height, prominence or FWHM &mdash; with <b>Refine by fitting</b>
            also the fitted values (also offered as x).</li>
    </ul>
    <p>For example the position against the temperature shows how a band shifts through a
    melting series, and the height against the position shows which bands are strong. The
    points are coloured by the <b>peak number</b> (1st, 2nd, &hellip; peak of each spectrum from
    low to high x), by <b>band</b> (the peaks of all spectra at the same position, within
    <b>same band within &plusmn;</b>, get one colour whatever their number), by <b>maximum /
    minimum</b>, or in one colour.</p>
    <p><b>Join the same &hellip;</b> draws lines from spectrum to spectrum through the same peak,
    each line in its own colour (named in the legend):</p>
    <ul>
        <li><b>peak number</b>: through the 1st peak of each spectrum, the 2nd, &hellip; The
            numbers count from low x, so when a peak is missing in some spectra (e.g. a band that
            disappears on heating) the numbers after it shift and a line jumps to the next
            band.</li>
        <li><b>band (peak by its position)</b> (chosen at the start): through the peaks at the
            same position. A line
            always stays on its band; where the band is not found it simply has no point. Use
            this to follow bands through a melting series.</li>
    </ul>
    <p>With x a value of the spectrum the line runs along x; with x a number of the peak (e.g. the
    height) it runs from spectrum to spectrum in the order of the list. Join is greyed out when x
    is the peak itself (its number or its position), where the points of one peak lie above each
    other. <b>Same band within &plusmn;</b> (shown when bands are used) sets how close two peaks
    must be to count as one band. <b>Only the selected rows</b> draws the rows selected in the
    table; <b>Legend</b> shows or hides the legend. <b>Copy plot</b> puts the plot on the
    clipboard for Word or PowerPoint; the toolbar zooms and saves it.</p>
    <h3 id="band-table">Tab Band table</h3>
    <p>The tab <b>Band table</b> turns the list round for Excel: <b>one row per spectrum</b> (in the
    order of the spectra list) and <b>one column per band</b> &mdash; the peaks of all spectra at the
    same position, within <b>same band within &plusmn;</b> (the same setting as in the tab Plot),
    named by their position (686, 1093, &hellip;). Each cell holds the chosen <b>Value</b> of that
    spectrum's peak in that band: position, height, prominence or FWHM &mdash; with <b>Refine by
    fitting</b> also the fitted position, FWHM, height, area or R&sup2;. An empty cell: the spectrum
    has no peak in that band (e.g. a band that disappears on heating). <b>Stored values</b> adds the
    values stored with the spectra (e.g. <code>temperature_C</code>, pH) as columns before the
    bands, so for example the area of every band against the temperature is ready to plot in
    Excel. If one spectrum has two or more peaks in one band (e.g. a band split in two), only the
    one nearest the band's position is shown and the line under the table says how many peaks
    were left out &mdash; lower the &plusmn; distance to give them their own columns. With
    this tab open, <b>Copy</b> (Ctrl+C) and <b>Export&hellip;</b> take the whole band table.</p>
    <p><b>Open in the Data table</b> opens the <a href="help://user_guide#values-per-spectrum">Data
    table</a> of the same spectra on its tab <i>Values per spectrum</i>, with one column per band
    (<b>b1, b2, &hellip;</b>, e.g. &ldquo;Height of the band at 686&rdquo;) of the value shown here,
    next to the values stored with the spectra. There you can calculate with them &mdash; e.g.
    <code>b2 / b1</code>, the ratio of two bands in every spectrum &mdash; and plot them against
    e.g. <code>temperature_C</code> without Excel.</p>
    @@PEAK_BAND_TABLE@@

    <hr>
    <h2 id="mark">Tab Mark on the plot</h2>
    <p>Right-click on the plot &rarr; <b>Detect Peaks</b> opens the window on this tab.
    <b>Mark the peaks on the plot</b> puts a red dot on every peak of the plotted spectra, found
    with the settings at the top, and writes its position as set here (<b>Labels</b>: once per
    band, on every peak, only the current spectrum or none; font size, rotation, decimals,
    number format, the position alone or with the height). The window stays open, and from then
    on the marks <b>follow every change</b> of a setting &mdash; the top ones and these &mdash;
    so you see at once what, e.g., a lower Prominence finds. <b>Remove the marks</b> removes
    them (also right-click on the plot &rarr; <b>Clear Peaks</b>, which also removes the fitted
    peaks drawn by <i>Show on the main plot</i>). Marking again replaces the old marks, so none
    are left behind. The settings are kept for the next time.</p>
    <p>Opened on this tab, the window lists the peaks only when you open one of the other tabs,
    so marking a large selection (e.g. a map) does not first list thousands of spectra.</p>

    <div class="tip">
        <strong>Tip:</strong> if a real, obvious dip or peak isn't being
        picked up, lower Prominence (a small band next to a big one), Signal-to-noise
        (a very weak band) or Distance (two bands close together) &mdash; Threshold is
        already 0. If noise is marked, raise Signal-to-noise.
    </div>

    </body></html>
    """
