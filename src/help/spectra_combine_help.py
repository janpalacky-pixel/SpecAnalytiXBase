# src/help/combine_spectra_help.py

def get_combine_spectra_help_title():
    """Return the title for spectral arithmetic help."""
    return "Combine Spectra Help"

def get_combine_spectra_help_content():
    """Return HTML content for spectral arithmetic help."""
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
            ul, ol { padding-left: 22px; }
            li { margin: 4px 0; }
        </style>
    </head>
    <body>
        <h1>Combine Spectra Help</h1>

        <h2>Overview</h2>
        <p>Combine Spectra creates one new spectrum by <b>averaging</b> or
        <b>summing</b> a selection of existing spectra, point by point along a
        shared x-axis.</p>
        <div class="tip">
            <strong>Primary use case:</strong> averaging multiple replicate
            measurements of the same sample is a standard way to improve the
            <b>signal-to-noise ratio (SNR)</b> of a spectrum.
        </div>

        <h2>Prerequisite: Identical X-Axes</h2>
        <div class="warn">
            <p><b>Important:</b> every spectrum being combined must share an
            <b>identical x-axis</b> &mdash; the same number of points and the same
            x-values. This is checked both in the live preview and before the
            operation actually runs, with a clear message naming the mismatch
            rather than a numeric error.</p>
            <p>If the selected spectra don't already match, use the
            <b>'Data Range'</b> operation with <b>'Apply linearization'</b> enabled
            first, to bring them onto a common, uniform x-axis.</p>
        </div>

        <h2>How to Use</h2>
        <ol>
            <li>Select two or more spectra with identical x-axes from the main
                spectrum list.</li>
            <li>In the 'Spectra Processing' panel, choose <b>'Combine Spectra'</b>
                from the dropdown and click <b>'Parameters'</b>.</li>
            <li>Choose <b>Average</b> or <b>Sum</b>, and set a name for the result
                spectrum. The <b>Preview</b> panel below updates automatically as
                you change either.</li>
            <li>Click <b>OK</b> to save the parameters, then <b>Run</b> in the
                'Spectra Processing' panel to execute the operation. Whether the
                result <em>replaces</em> the source spectra or is <em>added</em>
                alongside them is controlled by the <b>"Add as new"</b> checkbox in
                the main window's Spectra Processing panel &mdash; the same
                checkbox used by every other operation, not a setting inside this
                dialog.</li>
        </ol>

        <div class="tip">
            <strong>Save without running:</strong> the <strong>Save&hellip;</strong>
            button next to OK exports the current preview result directly to a
            file, without applying the operation to the main spectrum list or
            closing this dialog.
        </div>

        <h2>Selected Spectra List</h2>
        <p>The list at the top shows every spectrum selected for this operation.
        Selecting rows in this list does <em>not</em> change what gets combined
        &mdash; the actual average or sum always uses every spectrum selected in
        the main window. The list selection only controls which individual
        spectra are also drawn in the Preview, for visual comparison against the
        result.</p>
        <ul>
            <li><b>Select all</b> / <b>Clear</b> &mdash; quickly select or
                deselect every row.</li>
            <li><b>Show selected spectra with result</b> &mdash; when checked, the
                spectra currently selected in the list are drawn alongside the
                average/sum result in the Preview, rather than the result alone.</li>
            <li><b>Show legend</b> &mdash; toggles the plot legend in the Preview.
                Off by default, since a single result line rarely needs one.</li>
        </ul>

        <h2>Operation</h2>
        <ul>
            <li><b>Average Spectra:</b> the mean y-value at each x-value. The
                standard choice for improving SNR across replicate measurements.</li>
            <li><b>Sum Spectra:</b> the sum of y-values at each x-value.</li>
            <li><b>Show &plusmn;1 std-dev band:</b> only available for Average
                (variance around a Sum isn't a standard quantity, so this is
                disabled when Sum is selected). When checked, shades the region one
                <em>sample</em> standard deviation above and below the average at
                each point (dividing by N&minus;1, the standard convention for
                variability across a set of replicate measurements &mdash; the same
                convention used by Excel's STDEV, Origin, and GraphPad) &mdash; a
                quick visual sense of how much the replicates varied, without
                needing a separate calculation.</li>
        </ul>

        <h2>Output</h2>
        <p><b>New spectrum name:</b> the label given to the result spectrum in the
        main list. If the chosen name already exists, a numeric suffix is added
        automatically (e.g. <em>Avg_of_5_spectra_2</em>).</p>

        <div class="tip">
            <strong>Settings are remembered.</strong> Average/Sum, the output
            name, and the <b>Show selected spectra with result</b>, <b>Show
            legend</b>, and <b>Show &plusmn;1 std-dev band</b> checkboxes are all
            remembered the next time this dialog is opened for the same spectra
            selection &mdash; whether it was last closed with OK or with Cancel /
            the window's close button. <b>Shorten names</b> is the one exception:
            it is never remembered, consistent with every other dialog in the app.
        </div>

        <h2>Workflow Summary</h2>
        <ol>
            <li>Select two or more spectra with identical x-axes from the main spectrum list.</li>
            <li>In the 'Spectra Processing' panel, choose <b>'Combine Spectra'</b> from the dropdown and click <b>'Parameters'</b>.</li>
            <li>Configure the operation type and the name of the new spectrum, checking the Preview as you go.</li>
            <li>Click <b>OK</b> to save the parameters.</li>
            <li>Set <b>"Add as new"</b> in the main window if you want to keep the originals, then click <b>Run</b> in the 'Spectra Processing' panel to execute the operation.</li>
        </ol>
    <h2>Shorten Names</h2>
    <p>This dialog has its own independent <strong>Shorten names</strong>
    checkbox — separate from the main window's, and off by default
    regardless of the main window's setting. When checked, it applies to
    the Selected Spectra list.
    It only affects what is <em>displayed</em> — spectrum identity, and any
    name written into a new or exported spectrum, is always the full original
    label. Toggling the main window's Shorten names checkbox has no effect on
    this dialog.</p>

    </body>
    </html>
    """
