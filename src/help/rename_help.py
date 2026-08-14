# src/help/rename_help.py

def get_rename_help_title():
    return "Rename Spectra Help"

def get_rename_help_content():
    """Return HTML content for the Rename Spectra dialog's help."""
    return """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
            h1, h2 { color: #2E7D32; border-bottom: 2px solid #2E7D32; }
            h3 { color: #1976D2; margin-top: 1.5em; }
            .tip { background-color: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin-top: 10px; }
            .key-feature { background-color: #e3f2fd; padding: 10px; border-left: 4px solid #1e88e5; margin-top: 10px;}
            .warning { background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; }
            code { background-color: #f1f1f1; padding: 2px 4px; border-radius: 3px; font-family: monospace;}
            li { margin-bottom: 5px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { text-align: left; padding: 4px 8px; }
            tr:nth-child(even) { background: #f7f7f7; }
        </style>
    </head>
    <body>
        <h1>Rename Spectra Help</h1>

        <h2>Overview</h2>
        <p>Rename one or more spectra at once, from a table showing the
        current ("Original Label") and editable ("New Label") name side by
        side for every selected spectrum. Opens via right-click &rarr;
        <b>Rename</b> on the spectrum list, the <b>Rename</b> button below
        it, or <b>View &rarr; Rename spectra</b>.</p>

        <h2>Selecting which spectra to rename</h2>
        <ul>
            <li><b>Select All</b> / <b>Deselect All</b> — every row in the table.</li>
            <li><b>Select Spectra…</b> — opens a pattern-matching dialog to
                select rows by name, the same tool used elsewhere in the app
                for selecting spectra by pattern.</li>
        </ul>
        <p>Only <em>selected</em> rows are affected by right-click batch actions
        (Add Prefix, Add Suffix, Sequential Rename, Replace Text) and by
        Apply / Add as New — an unselected row's name is left exactly as
        typed (or untouched, if you never edited it).</p>

        <h2>Editing names</h2>
        <p>Double-click any cell in the "New Label" column to edit it
        directly, or use the right-click batch actions below to rename
        several rows at once according to a rule instead of typing each one
        individually.</p>

        <h3>Right-click batch actions (on selected rows)</h3>
        <table>
            <tr><th>Action</th><th>What it does</th></tr>
            <tr><td><b>Add Prefix…</b></td><td>Prepends the text you enter to every selected row's current New Label.</td></tr>
            <tr><td><b>Add Suffix…</b></td><td>Appends the text you enter to every selected row's current New Label.</td></tr>
            <tr><td><b>Sequential Rename…</b></td><td>Enter a pattern containing <code>#</code> (e.g. <code>sample_#</code>), a starting number, and how many digits to zero-pad to (e.g. 2 digits &rarr; 01, 02, &hellip;). Selected rows are numbered in their current table order starting from that number — <code>sample_#</code> starting at 1 with 2-digit padding gives <code>sample_01</code>, <code>sample_02</code>, and so on.</td></tr>
            <tr><td><b>Replace Text…</b></td><td>Find-and-replace across every selected row's current New Label. Rows where the search text isn't found are left unchanged; you're told how many rows were actually affected.</td></tr>
        </table>
        <div class="tip">
            <strong>These batch actions all work on whatever is currently
            in the "New Label" column</strong> — they can be combined and
            applied one after another (e.g. Add Prefix, then Sequential
            Rename on top of that), and none of them commit anything by
            themselves. Nothing actually changes until you click
            <b>Apply</b> or <b>Add as New</b>.
        </div>

        <h2>Apply vs. Add as New</h2>
        <ul>
            <li><b>Apply</b> — renames the spectra in place. The spectrum
                list is re-sorted afterward, since a new name can change
                where a spectrum belongs alphabetically.</li>
            <li><b>Add as New</b> — the original spectra are left completely
                untouched, and new copies are added to the list under the
                new names instead. Useful when you want to keep both the old
                and new names as separate, independent spectra.</li>
        </ul>
        <div class="warning">
            If any spectrum you're renaming already appears in earlier
            Operations History steps, applying a rename doesn't retroactively
            change those older steps — they keep showing whichever name was
            genuinely in use at that point in time. You'll be asked to
            confirm before an in-place rename proceeds, specifically because
            this can look confusing when paging back through history later:
            an older step showing an unfamiliar name isn't a bug, it's simply
            what that spectrum was called at that point.
        </div>

        <h2 id="history">Previous names are tracked automatically</h2>
        <p>Every rename — whether from Apply or Add as New, and whether it's
        one spectrum or a whole batch — is recorded in that spectrum's own
        metadata. Right-click a spectrum in the main list &rarr;
        <b>Show Metadata</b>, and look under <b>Correction History</b> for an
        entry like:</p>
        <div class="tip" style="font-family: monospace; background-color: #f1f1f1; border-left: 4px solid #888;">
            Rename<br>
            Previous Label: uvvis_2comp_clean : uv_02<br>
            New Label: spA
        </div>
        <p>If a spectrum has been renamed more than once, every rename shows
        up as its own entry, in order — so you can always see the spectrum's
        full naming history, not just what it was called immediately before
        its current name. This history is tracked correctly no matter what
        else you do to the spectrum in between renames (smoothing, baseline
        correction, or anything else) — each rename is recorded against that
        specific spectrum individually, and stays attached to it going
        forward.</p>

        <div class="key-feature">
            <strong>Why this matters:</strong> if you're looking at a
            spectrum called <code>spC</code> and want to know what it used
            to be called before you renamed it (perhaps to match it back up
            with an external file, or to understand an older plot legend),
            its Correction History has the full answer — you don't need to
            remember the renaming steps yourself.
        </div>
    </body>
    </html>
    """
