# src/help/plot_controls_help.py


def get_plot_controls_help_title():
    return "Interactive Update & Legend — Performance Guide"


def get_plot_controls_help_content():
    return """
    <html>
    <head>
        <style>
            body  { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1    { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h2    { color: #1976D2; margin-top: 28px; border-bottom: 1px solid #BBDEFB; padding-bottom: 4px; }
            h3    { color: #F57C00; margin-top: 18px; }
            .tip     { background-color: #d4edda; border: 1px solid #c3e6cb; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .warning { background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 10px; border-radius: 5px; margin: 8px 0; }
            .info    { background-color: #e3f2fd; padding: 10px; margin: 8px 0; border-left: 4px solid #2196f3; border-radius: 0 5px 5px 0; }
            table { width: 100%; border-collapse: collapse; margin: 10px 0; }
            th    { background-color: #E3EAF4; color: #1976D2; padding: 7px 10px; text-align: left; }
            td    { padding: 6px 10px; border-bottom: 1px solid #E0E0E0; }
            tr:nth-child(even) { background-color: #F8F9FB; }
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
        </style>
    </head>
    <body>

    <h1>Interactive Update &amp; Legend — Performance Guide</h1>

    <p>Two controls below the spectrum list have a significant impact on performance
    when working with large datasets: <strong>Interactive Update</strong> and
    <strong>☰ Legend</strong>. Understanding the trade-offs helps you work efficiently
    with any dataset size.</p>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <h2>Interactive Update</h2>

    <p><strong>What it does:</strong> when checked, the plot redraws automatically
    every time you change the spectrum selection — click one spectrum, the plot
    updates; click another, it updates again immediately.</p>

    <p><strong>Why it can be slow:</strong> every selection change triggers a full
    matplotlib render of all selected spectra. With 10–50 spectra this is
    imperceptible. With 500–5000 spectra each redraw can take several seconds,
    making the application feel unresponsive while you are simply trying to
    navigate the list.</p>

    <div class="tip">
        <strong>Recommendation — Interactive Update ON (default):</strong>
        keep it checked for everyday work with small to medium datasets (&lt;200 spectra).
        You get instant visual feedback as you explore your data.
    </div>

    <div class="warning">
        <strong>Recommendation — Interactive Update OFF (large datasets):</strong>
        uncheck it when working with hundreds or thousands of spectra. The plot is
        cleared when you change the selection, and nothing is redrawn until you press
        <strong>Refresh Plot</strong>. This lets you build your selection freely
        (e.g. Select All, then deselect outliers) without paying the rendering cost
        after every single click.
    </div>

    <div class="note">
        This applies to applying a processing operation (SNIP baseline,
        normalization, Data range, etc.) via <strong>Apply</strong>/<strong>Add as
        New</strong>, not just to changing your selection by hand. With Interactive
        Update off, committing an operation updates the spectrum list and
        selection as usual but does not redraw the plot or re-check the box for
        you &mdash; press <strong>Refresh Plot</strong> when you want to see the
        result.
    </div>

    <h3>Typical workflow with large datasets</h3>
    <ol>
        <li>Uncheck <strong>Interactive Update</strong>.</li>
        <li>Select the spectra you want (Select All, range select, Ctrl+click, etc.).</li>
        <li>Press <strong>Refresh Plot</strong> once when the selection is ready.</li>
        <li>Review the plot; adjust the selection if needed and press Refresh Plot again.</li>
    </ol>

    <h2 id="many-spectra">Plotting thousands of spectra: preview, Plot all, Stop</h2>
    <p>Drawing is the slow part of plotting many spectra: about 5&nbsp;s per 1&nbsp;000 spectra
    of 1&nbsp;600 points on a typical computer, almost all of it one single drawing step that
    cannot show progress or be interrupted. Therefore, when <b>more than 2&nbsp;000</b> spectra
    are selected, the <b>Overlay</b>, <b>Grid</b> and <b>Waterfall</b> plots show a
    <b>preview</b>: 1&nbsp;000 evenly spread spectra (always the first and the last). A line
    above the plot says so, e.g. <i>"Preview: 1 000 of 21 000 selected spectra drawn (evenly
    spread). Analyses use all 21 000."</i></p>
    <ul>
        <li><b>Your selection is not changed.</b> Every analysis and processing step uses all
        selected spectra; only the picture shows fewer.</li>
        <li><b>Plot all</b> (on that line) draws every selected spectrum. The Overlay plot is
        then drawn in portions of 500 spectra with a progress window
        (<i>"Plotting spectra… 3 500 / 21 000"</i>) and a <b>Stop</b> button.</li>
        <li><b>Stop</b> keeps the spectra drawn so far, removes the rest from the plot and
        switches <b>Interactive Update</b> off, so the next selection change does not start
        a long drawing again. The line above the plot says how many were drawn; press
        Refresh Plot or Plot all to draw again.</li>
        <li><b>View &rarr; Plotting many spectra&hellip;</b> (also <b>Settings&hellip;</b> on
        that line): the limit (default 2&nbsp;000), the preview size (default 1&nbsp;000), or
        <i>Always plot all</i>. Remembered between sessions.</li>
        <li><b>Tool windows</b> (FFT Denoising, X-axis alignment, Isosbestic Point
        Detection, 2D Correlation, Normalization, Data range, Spectral Calculator, ROI
        spectra, &hellip;) redraw their plots after every change, so they draw at most
        <b>100</b> spectra (an evenly spread subset; the plot says e.g. <i>"100 of 3&nbsp;000
        shown"</i>). Their calculations always use all spectra. The number is set in the same
        window: <i>Tool windows: draw at most &hellip; spectra</i>.</li>
        <li>Not limited: <b>Heatmap</b> (one image, fast), <b>Mean&nbsp;&plusmn;&nbsp;SD</b> and
        <b>Difference</b> (their mean must be the mean of all selected spectra) and
        <b>Single spectrum</b>.</li>
        <li>Zooming or panning a plot with all spectra redraws all of them at once again;
        for exploring, the preview is much quicker.</li>
    </ul>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <h2>☰ Legend</h2>

    <p><strong>What it does:</strong> adds a legend to the plot that labels each
    spectrum by name. Useful for identifying individual lines when comparing a small
    number of spectra.</p>

    <p><strong>On by default (since 1.5):</strong> the legend lists at most <em>Maximum Legend
    Items</em> entries (default 20), so it stays quick and readable also with thousands of
    spectra (see <i>Limiting legend size</i> below). Only <em>Show all</em> with hundreds of
    spectra is slow &mdash; matplotlib must lay out and draw one text entry per spectrum, and
    beyond ~50 entries the legend is unreadable anyway. To switch it off: untick
    <em>show legend</em> in <i>Basic plot options</i> (under <i>automatic line colors</i>; it
    hides the legend at once, without plotting again); ☰ Legend opens its settings.</p>

    <h3>When to enable the legend</h3>
    <table>
        <tr><th>Situation</th><th>Legend</th><th>Reason</th></tr>
        <tr>
            <td>Overlay plot, &lt;20 spectra</td>
            <td>✅ Enable</td>
            <td>Readable and useful for identifying individual lines</td>
        </tr>
        <tr>
            <td>Grid plot (any number)</td>
            <td>✅ Enable</td>
            <td>Each panel shows one spectrum — the legend title identifies it.
                Without a legend, grid panels are unlabelled and hard to interpret.</td>
        </tr>
        <tr>
            <td>Overlay / Waterfall, 20–50 spectra</td>
            <td>⚠️ Optional</td>
            <td>Starting to get crowded; more than Maximum Items (20) are listed evenly spread</td>
        </tr>
        <tr>
            <td>Overlay / Waterfall, &gt;50 spectra</td>
            <td>✅ Fine (limited)</td>
            <td>20 evenly spread entries are listed (quick); avoid <em>Show all</em> &mdash;
                hundreds of entries are unreadable and slow</td>
        </tr>
        <tr>
            <td>Heatmap / Mean±SD / Difference</td>
            <td>❌ Usually off</td>
            <td>These plot types summarise data — individual labels add little value</td>
        </tr>
    </table>

    <div class="info">
        <strong>Grid plot note:</strong> the legend is especially important in Grid
        plot mode because there is no other way to know which panel corresponds to
        which spectrum. If you use Grid plots regularly, enable the legend and keep
        it enabled — grid plots rarely contain hundreds of panels so the performance
        cost is acceptable.
    </div>

    <h3>Limiting legend size</h3>
    <p>The legend lists at most <em>Maximum Legend Items</em> entries (☰ Legend, default 20).
    With more spectra it lists an <b>evenly spread</b> subset &mdash; the first, the last and
    spectra evenly in between, like the preview of very many spectra &mdash; and the orange
    strip above the plot says so, e.g. <i>Legend: 20 of 4&nbsp;675 spectra listed (evenly
    spread)</i>, with these buttons:</p>
    <ul>
      <li><b>Show all</b> &mdash; list every entry. This ticks <em>Show All Legend Items</em>
      in the ☰ Legend window, so it stays on for the next plots (untick it there to go back).
      Above 500 entries it asks first: such a legend is slow to draw and covers the plot.</li>
      <li><b>Choose…</b> &mdash; pick the spectra to list, in the same window as
      <em>Select spectra</em> (by name, range or every n-th; Select / Add / Remove). The choice
      is kept while the same spectra are plotted; <b>Evenly spread</b> forgets it.</li>
      <li><b>Settings…</b> &mdash; the ☰ Legend window (maximum number, position, font, …).</li>
    </ul>
    <p>When a preview of very many spectra is drawn, the legend lists entries of the drawn
    spectra only; both notes then share the strip.</p>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <h2>Combined recommendations by dataset size</h2>

    <table>
        <tr><th>Dataset size</th><th>Interactive Update</th><th>Legend</th></tr>
        <tr><td>&lt;50 spectra</td>  <td>✅ On</td> <td>✅ On (if needed)</td></tr>
        <tr><td>50–200 spectra</td>  <td>✅ On</td> <td>✅ On (limited to 20)</td></tr>
        <tr><td>200–1000 spectra</td><td>⚠️ Off — use Refresh Plot</td><td>✅ On (limited to 20)</td></tr>
        <tr><td>&gt;1000 spectra</td><td>❌ Off — use Refresh Plot</td><td>✅ On (limited to 20)</td></tr>
    </table>
    <p>Above 2&nbsp;000 selected spectra the Overlay, Grid and Waterfall plots show a preview
    anyway (see <a href="#many-spectra">Plotting thousands of spectra</a>), so Interactive
    Update stays quick enough to leave on.</p>

    <div class="tip">
        For more details on plot types and the full feature set, see the
        <a href="help://user_guide">User Guide</a>.
    </div>

    </body>
    </html>
    """
