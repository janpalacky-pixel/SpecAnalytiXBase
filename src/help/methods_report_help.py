# src/help/methods_report_help.py

def get_methods_report_help_title():
    return "Methods Report for Publication Help"


def get_methods_report_help_content():
    """HTML help for File -> Methods report for publication."""
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; max-width: 950px; }
            h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { color: #1976D2; margin-top: 1.5em; }
            .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin-top: 10px; }
            .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin-top: 10px; }
            .example { background-color: #f5f5f5; padding: 10px; border-left: 4px solid #999; font-style: italic; }
            li { margin-bottom: 5px; }
            table { border-collapse: collapse; }
            th, td { text-align: left; padding: 4px 8px; border: 1px solid #ccc; }
        </style>
    </head>
    <body>
        <h1>Methods Report for Publication</h1>

        <h2>What it is</h2>
        <p><b>File &rarr; Methods report for publication&hellip;</b> writes a first draft
        of the data-processing part of a paper's <i>Methods</i> section. It describes
        every step in the <b>Operations History up to the active step</b> &mdash; that
        is, exactly the processing behind the spectra shown in the main window &mdash;
        with the settings that were used and references to the original publications of
        the methods. To describe an earlier state, go back to that step in the
        Operations History first, then open the report.</p>
        <div class="example">"The baseline was estimated and subtracted by asymmetrically
        reweighted penalized least squares (arPLS) [2] with &lambda; = 10&#8309; and at
        most 50 iterations. The spectra were smoothed with a Savitzky&ndash;Golay filter
        [3, 4] (window 11 points, polynomial order 3)."</div>

        <div class="warning"><b>A template, not a finished text.</b> The report is
        generated automatically from the recorded settings, so it can be worded
        awkwardly, be more detailed than a journal needs, or occasionally be inaccurate
        &mdash; this feature is new and still being refined. The program also knows only
        the settings, not your scientific context. Always read it, check it against what
        you did, and adapt it freely before using it in a manuscript.</div>

        <h2>The three tabs</h2>
        <p>All three can be edited; what you copy or save is always the edited
        version.</p>
        <h3>Text</h3>
        <p>The Methods paragraph. Edit it like any text. Typical changes:</p>
        <ul>
            <li>Make it specific: a generated phrase such as <i>"applied to 11 of 636
            spectra"</i> is exact but not very informative &mdash; you might rewrite it as
            <i>"the 11 Raman spectra of sample A were &hellip;"</i>.</li>
            <li>Add what the program cannot know: sample preparation, instrument,
            acquisition settings, or why a step was done.</li>
            <li>Shorten it to the level of detail your journal expects, or merge steps.</li>
            <li>Change the citation style in the text, for example from <i>[2]</i> to
            <i>(Baek et al., 2015)</i>.</li>
        </ul>
        <h3>Parameters</h3>
        <p>Every step with its settings: <b>Step</b>, <b>Operation</b>, <b>Applied
        to</b> (how many spectra), <b>Parameter</b> and <b>Value</b> &mdash; useful as a
        table in the Supporting Information. Double-click a cell to change it, for example
        to add a comment or simplify a value.</p>
        <h3>References</h3>
        <p>The original publications of the methods used, numbered in the order they
        are first cited in the text, plus SpecAnalytiXBase itself [1]. One reference per
        paragraph (separated by an empty line). You can rewrite them in your journal's
        citation style, although usually it is easier to paste them into your reference
        manager or to leave them out (see below) and cite in your own format.</p>
        <p>If you change the numbers or the order here, change the citations in the
        Text tab to match &mdash; the two are not linked once you start editing.</p>

        <h2>Choosing what to copy or save</h2>
        <p>The text is always included. Below the tabs, tick what should go with it:</p>
        <table>
            <tr><th>Parameter table</th><th>References</th><th>Typical use</th></tr>
            <tr><td>&#10003;</td><td>&#10003;</td><td>Complete record, e.g. for Supporting Information or a lab notebook.</td></tr>
            <tr><td></td><td>&#10003;</td><td>Methods text with its reference list.</td></tr>
            <tr><td>&#10003;</td><td></td><td>Text with the detailed parameters, e.g. when you cite in your own format.</td></tr>
            <tr><td></td><td></td><td>Only the paragraph &mdash; you add the citations in your own format.</td></tr>
        </table>
        <p>Your choice is remembered for next time.</p>

        <h2>Copy and Save</h2>
        <ul>
            <li><b>Copy</b> puts the text and the ticked parts on the clipboard. Pasted
            into Word (or LibreOffice, Google Docs), headings and the table keep their
            formatting; pasted into a plain-text editor, you get plain text.</li>
            <li><b>Save&hellip;</b> writes a file:
                <ul>
                    <li><b>Word document (.docx)</b> &mdash; the default; opens directly
                    in Word, LibreOffice or Google Docs.</li>
                    <li><b>HTML</b> &mdash; opens in any browser, and in Word.</li>
                    <li><b>Markdown (.md)</b> &mdash; for Overleaf/LaTeX workflows, GitHub
                    or notes.</li>
                    <li><b>Text (.txt)</b> &mdash; plain text.</li>
                </ul>
                The file is saved in the folder of your data by default.</li>
        </ul>

        <h2>Good to know</h2>
        <ul>
            <li>Renaming spectra is not mentioned; it does not change the data.</li>
            <li>If a step was applied to only some of the spectra, the text says how many,
            e.g. <i>"(applied to 15 of 30 spectra)"</i> &mdash; worth rewriting in your own
            words, e.g. <i>"the 15 spectra of sample A"</i>.</li>
            <li>A saved processing pipeline is described step by step.</li>
            <li>Analysis results such as peak fitting or melting curves are described only
            briefly; report their results in your own words.</li>
            <li>The version of SpecAnalytiXBase and of the main calculation libraries
            (NumPy, SciPy) is included, so that the processing can be reproduced.</li>
            <li><b>Your edits are kept</b> when you close the window, also by accident, for
            the rest of the session. Opened again on the same processing, the report shows
            your edited version. If the processing has changed in the meantime, you are
            asked whether to keep your edited version or start from a new draft.
            <b>Restore generated draft</b> discards your edits and shows the automatic
            version again. Edits are not kept after the program is closed &mdash; save the
            report to keep them.</li>
        </ul>
        <div class="tip"><b>Tip:</b> The report always describes the processing as it is
        <i>now</i>. When you make the figures for a paper, save the report right away,
        next to the figures, and save a snapshot (File &rarr; Save) as well. If you later
        change or continue the processing, the saved report still describes exactly how
        those figures were made, and the snapshot lets you return to that state &mdash; a
        new report can then be generated from it at any time.</div>
    </body>
    </html>
    """
