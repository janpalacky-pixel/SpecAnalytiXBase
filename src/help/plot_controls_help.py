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

    <h3>Typical workflow with large datasets</h3>
    <ol>
        <li>Uncheck <strong>Interactive Update</strong>.</li>
        <li>Select the spectra you want (Select All, range select, Ctrl+click, etc.).</li>
        <li>Press <strong>Refresh Plot</strong> once when the selection is ready.</li>
        <li>Review the plot; adjust the selection if needed and press Refresh Plot again.</li>
    </ol>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <h2>☰ Legend</h2>

    <p><strong>What it does:</strong> adds a legend to the plot that labels each
    spectrum by name. Useful for identifying individual lines when comparing a small
    number of spectra.</p>

    <p><strong>Why it is off by default:</strong> generating a legend for hundreds of
    spectra is slow — matplotlib must lay out, render, and position one text entry per
    spectrum. With 500 spectra the legend generation alone can double the total
    rendering time. Beyond ~50 entries a legend also becomes unreadable anyway, so the
    performance cost produces no useful information.</p>

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
            <td>Starting to get crowded; use Maximum Items to cap entries shown</td>
        </tr>
        <tr>
            <td>Overlay / Waterfall, &gt;50 spectra</td>
            <td>❌ Disable</td>
            <td>Legend is unreadable and slows rendering significantly</td>
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
    <p>If you want a legend but have many spectra, open <strong>☰ Legend</strong>
    and uncheck <em>Show All Legend Items</em>. Set <em>Maximum Legend Items</em> to
    a manageable number (e.g. 20). Only the first N spectra will be labelled, keeping
    rendering fast while still providing some identification.</p>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <h2>Combined recommendations by dataset size</h2>

    <table>
        <tr><th>Dataset size</th><th>Interactive Update</th><th>Legend</th></tr>
        <tr><td>&lt;50 spectra</td>  <td>✅ On</td> <td>✅ On (if needed)</td></tr>
        <tr><td>50–200 spectra</td>  <td>✅ On</td> <td>⚠️ Off or limited</td></tr>
        <tr><td>200–1000 spectra</td><td>⚠️ Off — use Refresh Plot</td><td>❌ Off</td></tr>
        <tr><td>&gt;1000 spectra</td><td>❌ Off — use Refresh Plot</td><td>❌ Off</td></tr>
    </table>

    <div class="tip">
        For more details on plot types and the full feature set, see the
        <a href="help://user_guide">User Guide</a>.
    </div>

    </body>
    </html>
    """
