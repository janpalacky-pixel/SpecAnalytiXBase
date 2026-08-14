# src/help/save_help.py

def get_save_help_title():
    return "Save Spectra — Help"


def get_save_help_content():
    """Return HTML content for the Save Options dialog help."""
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { color: #1976D2; margin-top: 1.5em; }
            .tip     { background-color: #d4edda; padding: 10px;
                       border-left: 4px solid #28a745; margin-top: 10px; }
            .info    { background-color: #e3f2fd; padding: 10px;
                       border-left: 4px solid #1e88e5; margin-top: 10px; }
            .warning { background-color: #fff3cd; padding: 10px;
                       border-left: 4px solid #ffc107; margin-top: 10px; }
            code { background-color: #f1f1f1; padding: 2px 4px;
                   border-radius: 3px; font-family: monospace; }
            table { border-collapse: collapse; width: 100%; margin-top: 8px; }
            th { background: #e3f2fd; padding: 6px 10px;
                 border: 1px solid #bbb; text-align: left; }
            td { padding: 5px 10px; border: 1px solid #ddd; vertical-align: top; }
            li { margin-bottom: 5px; }
            pre { background:#f5f5f5; padding:8px; border-radius:4px;
                  font-family: monospace; font-size: 9pt; }
        </style>
    </head>
    <body>

    <h1>Save Spectra — Help</h1>

    <h2>Overview</h2>
    <p>
        The Save dialog lets you export the currently selected spectra to a
        file, or save the complete application state as a snapshot.
        Only the spectra highlighted in the spectrum list are saved —
        unselected spectra are not included.
    </p>

    <h2>File Format</h2>

    <h3>Text</h3>
    <p>
        Saves spectra as a plain-text file (<code>.txt</code> or
        <code>.csv</code>). You can control the column separator and decimal
        separator in the Options section. Text files can be opened in Excel,
        any text editor, or re-imported into this application.
    </p>

    <h3>Excel</h3>
    <p>
        Saves spectra as an Excel workbook (<code>.xlsx</code>). Numbers are
        stored as native Excel floats so there is no decimal-separator
        ambiguity. The sheet is named <b>spectra</b> so it can be
        automatically detected on re-import.
    </p>
    <p>
        The Value separator and Decimal separator options are not applicable
        to Excel files and are disabled when Excel is selected.
    </p>

    <h3>GRAMS (.spc)</h3>
    <p>
        Saves spectra in the Thermo/GRAMS Universal Data Format
        (<code>.spc</code>) — the same binary format read by this app's own
        SPC importer, and widely readable by other spectroscopy software
        (GRAMS/32 and descendants, and many instrument vendors' own
        tools). Files are written in the modern new-format header, with
        Y-values as IEEE float32 and the x-axis stored explicitly (not
        assumed evenly spaced), so re-importing a saved file reproduces the
        original values to float32 precision.
    </p>
    <div class="warning">
        <b>Save as Table with GRAMS requires a common x-scale — this isn't
        optional for this format.</b> A single <code>.spc</code> file's
        spectra (its "subfiles") all share exactly one x-axis by
        construction; there's no equivalent of the text/Excel "individual
        x-scales" interlaced layout for this format. <b>Use common
        x-scale</b> is automatically checked and locked when GRAMS is
        selected in Table mode, and saving is rejected with a clear message
        if the selected spectra don't actually share one axis. If your
        spectra have different x-scales, use <b>Save Individual Files</b>
        instead — one <code>.spc</code> file per spectrum, no shared-axis
        requirement.
    </div>
    <p>
        Layout (Columns/Rows), Include column labels, and the separator
        options don't apply to this format — it's binary, not delimited
        text — so those controls are hidden when GRAMS is selected.
    </p>

    <h3>Snapshot</h3>
    <p>
        Saves the <b>complete application state</b> — not just the spectrum
        data, but also which spectra are selected, the full operations history
        (baseline correction, normalisation, data range, etc.), and all plot
        settings. The file extension is <code>.snapx</code>.
    </p>
    <p>
        Use a snapshot when you want to continue working from exactly the
        same point in a future session. To restore a snapshot use
        <b>File → Import Snapshot</b>.
    </p>
    <div class="info">
        When Snapshot is selected, all other options (Save Mode, X-scale,
        Options) are disabled — a snapshot always saves the full state.
    </div>

    <h2>Save Mode</h2>

    <h3>Save as Table</h3>
    <p>
        All selected spectra are saved into a <b>single file</b> as columns.
        See the X-scale section below for details of the column layout.
    </p>

    <h3>Save Individual Files</h3>
    <p>
        Each spectrum is saved as its own <b>separate file</b> in a directory
        you choose. Each file contains two columns: the x-scale and the
        y-scale for that spectrum. The filename is derived from the spectrum
        label.
    </p>

    <h2>X-scale  <small>(Save as Table only)</small></h2>

    <h3>Use common x-scale</h3>
    <p>
        When all selected spectra share the same x-scale grid, enable this
        option. The file will have one shared x-scale column followed by one
        y-scale column per spectrum:
    </p>
    <pre>
x_scale    spectrum_A    spectrum_B    spectrum_C
100.0      1.23          4.56          7.89
102.0      1.31          4.61          7.92</pre>
    <p>
        This is the simplest layout and can always be re-imported without
        any special settings.
    </p>
    <div class="warning">
        If the selected spectra do not all share the same x-scale, this
        option will be rejected with a warning when you click Save.
    </div>

    <h3>Layout: Columns / Rows  <small>(only shown when "Use common x-scale" is checked)</small></h3>
    <p>
        Choose whether the saved file has spectra in columns (the default,
        matching the layout shown above) or in <b>rows</b> instead —
        spectra become rows, sharing the x-scale in the header row:
    </p>
    <pre>
           100.0    102.0    104.0
spectrum_A   1.23     1.31     1.38
spectrum_B   4.56     4.61     4.65</pre>
    <p>
        A small <b>?</b> button next to Layout explains why this option
        only appears with "Use common x-scale" checked: Rows layout needs
        one shared X-axis to move into the header row, and "Individual
        x-scales" (below) has no single shared axis to use that way, so
        Layout stays column-only in that case.
    </p>
    <div class="warning">
        <b>Re-importing Rows-layout files:</b> select <b>Row-oriented</b>
        in the Import dialog's Layout option. No other setting is needed —
        the file round-trips directly.
    </div>

    <div class="info">
        <b>Why does orientation (columns vs. rows) matter at all?</b> This
        app always stores spectra internally the same way regardless of
        which layout you save as — Columns/Rows here is purely an output
        choice. But orientation does matter once you use the data
        elsewhere, e.g. in PCA (rows and columns play different, non-
        interchangeable roles there). See
        <a href="help://import">"How This App Represents Your Data" in the
        Import help</a> for the fuller explanation — it's written from the
        import side but applies equally here.
    </div>

    <h3>Individual x-scales (common x-scale unchecked)</h3>
    <p>
        When spectra have different x-scale grids, each spectrum gets its own
        x-scale column alongside its y-scale column. The columns alternate:
        x<sub>1</sub>, y<sub>1</sub>, x<sub>2</sub>, y<sub>2</sub>, …
    </p>
    <pre>
x_A      spectrum_A    x_B      spectrum_B
100.0    1.23          200.0    5.67
102.0    1.31          201.0    5.71</pre>
    <div class="warning">
        <b>Re-importing interlaced files:</b> when re-importing a file saved
        with individual x-scales, you must enable <b>Interlaced Format</b>
        in the Import dialog. The Import dialog shows a reminder about this.
    </div>

    <h2>Options</h2>

    <h3>Include column labels (header row)</h3>
    <p>
        When checked, the first row of the file contains column names
        (the spectrum labels). When unchecked, the file starts immediately
        with numeric data and columns are numbered automatically on
        re-import.
    </p>
    <p>
        Recommended: leave this checked so spectrum names are preserved
        on re-import.
    </p>

    <h3>Value separator  <small>(Text format only)</small></h3>
    <table>
        <tr><th>Option</th><th>Character</th><th>Typical use</th></tr>
        <tr><td><b>tab</b></td><td><code>\t</code></td>
            <td>Best choice — compatible with Excel and all import tools</td></tr>
        <tr><td><b>;</b></td><td>Semicolon</td>
            <td>European CSV convention</td></tr>
        <tr><td><b>,</b></td><td>Comma</td>
            <td>Only safe when decimal separator is a dot</td></tr>
        <tr><td><b>space</b></td><td>Space</td>
            <td>Some legacy instrument formats</td></tr>
    </table>

    <h3>Decimal separator  <small>(Text format only)</small></h3>
    <table>
        <tr><th>Option</th><th>Use when</th></tr>
        <tr><td><b>.</b> (dot)</td>
            <td>Sharing files with English-locale software or instruments</td></tr>
        <tr><td><b>,</b> (comma)</td>
            <td>Sharing files with European-locale software (German, Czech, French…)</td></tr>
    </table>
    <div class="warning">
        Never use comma as both the value separator and the decimal separator
        — the file will be unreadable. Use semicolon or tab as the value
        separator when the decimal separator is a comma.
    </div>

    <div class="tip">
        <b>Tip — best settings for round-tripping:</b> Tab separator +
        dot decimal + common x-scale (when possible) + labels enabled
        produces files that re-import correctly with zero settings adjustment.
    </div>

    </body>
    </html>
    """
