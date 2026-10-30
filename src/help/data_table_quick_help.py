# src/help/data_table_quick_help.py
"""The short texts of the orange "?" buttons of the Data table: one per tab,
each with a link to its section of the User Guide (user_guide_help.py)."""

QUICK_HELP = {
    'points': ("Quick help – Points (one row per x)", 'data-table-points', """
<p>This tab shows <b>the spectra themselves</b>: the first column is <b>x</b>, then one column
per spectrum, <b>sp1, sp2, &hellip;</b> (the end of its name under it).</p>
<p><b>New column =</b> calculates a new spectrum point by point, e.g. <code>sp1 - sp2</code>,
<code>sp1 / sp2</code>, <code>mean(sp1, sp2)</code> or <code>mean(all)</code> (more under
<b>Functions</b>). It appears as a green column f1, f2, &hellip;</p>
<p><b>Add formula columns as new spectra</b> puts them into the spectra list (Undo removes
them again).</p>
<p>For <b>one number per spectrum</b> &ndash; the area of a band, a peak height, a temperature
&ndash; use the tab <b>Values per spectrum</b>.</p>
<p>Select cells and press <b>Ctrl+C</b> to paste them into Excel. The measured spectra are
not changed here. The formula columns are there again when you open the Data table with the
same spectra.</p>
"""),
    'values': ("Quick help – Values per spectrum", 'values-per-spectrum', """
<p><b>Each row is one spectrum</b>, described by numbers:</p>
<ul>
<li>values stored with it, e.g. <code>temperature_C</code>;</li>
<li>the numbers in its name: <code>n1, n2, &hellip;</code>;</li>
<li>values you add: <b>Add value&hellip;</b> (blue v1, v2, &hellip;: e.g. the area or the
maximum of a band), the bands of the Peaks window's Band table (b1, &hellip;) or Peak
Fitting results (p1, &hellip;);</li>
<li>formulas of these columns: <b>New column =</b>, e.g. <code>v1 / v2</code> (green f1,
&hellip;).</li>
</ul>
<p><b>Plot</b> one column against another &ndash; e.g. the maximum of a band against
<code>temperature_C</code> gives a melting curve &ndash; or add it to the spectra list with
<b>As new spectrum</b>.</p>
<p>A range that reaches beyond the spectra is narrowed to where they have data (a note
says so).</p>
<p>Your columns are there again the next time you open the Data table - also after a restart, and in a snapshot.</p>
<p>To calculate with the spectra point by point, use the tab <b>Points (one row per x)</b>.</p>
<p>Select cells and press <b>Ctrl+C</b> to paste them into Excel.</p>
"""),
}


def quick_help_button(key, on_click):
    """The small orange "?" that opens the quick help of one tab."""
    from src.views.icons import help_button
    b = help_button(QUICK_HELP[key][0])
    b.clicked.connect(lambda: on_click(key))
    return b


def show_quick_help(parent, key, run=True):
    """The quick help of one tab; Full help... opens its section of the User
    Guide. run=False returns the message box without showing it (tests)."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QMessageBox
    title, anchor, html = QUICK_HELP[key]
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.RichText)
    box.setText(html)
    full = box.addButton("Full help…", QMessageBox.HelpRole)
    box.addButton(QMessageBox.Close)
    if not run:
        return box
    box.exec_()
    if box.clickedButton() is full:
        from src.help.help_window import open_help_topic
        open_help_topic(parent, 'user_guide', anchor)
    return box
