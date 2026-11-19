# src/help/quick_reference_help.py
"""Help -> Quick reference: one page with the mouse on the plot, the keys
and the right-click menus - what is in the program but not visible until
someone shows it. Printable on one A4 page, landscape (Ctrl+P in the
browser); the note on how to print is not printed.

The rows are data (COLUMNS), written in a small markup:
    [Ctrl]+[S]   keys, drawn as key caps (<kbd>)
    *text*       italic (an item of a menu)
    **text**     bold
tests/test_quick_reference.py checks that every key combination named here
is in keyboard_shortcuts.SHORTCUTS and that every menu item named here is in
the program's right-click menus - so the page cannot drift from the program
unnoticed. When a shortcut or a menu item changes, change it here too."""

import html
import re

TITLE = "Quick reference"

# (heading, accent, rows [(key, what)], note)   accent: 'blue' or 'orange'
COLUMNS = [
    [
        ("The plot – mouse", 'blue', [
            ("Mouse wheel", "Zoom the x axis around the pointer"),
            ("[Ctrl] + wheel", "Zoom the y axis"),
            ("Hold left button", "Move (pan) the plot"),
            ("Home / ← →", "Toolbar: whole range / back, forward"),
            ("Point at a line", "Shows its spectrum's name"),
            ("Click a line", "Finds the spectrum in the list"),
            ("Click legend name", "Hides the spectrum; click again: shows it"),
            ("Hover a list name", "Its line is drawn thicker, on top"),
            ("[Esc]", "Ends Zoom / Pan; again: Cursor off"),
        ], "Wheel and drag work the same in the plots of the tool windows "
           "(Peak Fitting, PCA, 2D Map, …)."),
        ("Basic plot options", 'blue', [
            ("Plot type", "Overlay, Grid, Waterfall, Mean ± SD, Difference, Heatmap"),
            ("Line colours", "Automatic, your own, or **by value** (e.g. temperature, "
                             "with a colour bar)"),
            ("Cursor", "Reads the values at the pointer; a click adds a band marker"),
            ("keep zoom", "A zoomed band stays while you step through spectra ([↑] [↓]); "
                          "y fits itself. Orange note: *Zoomed … – Home shows all*"),
            ("scale each", "Each spectrum drawn 0–1 to compare **shapes** of very different "
                           "intensities. Only the drawing – the data stay"),
            ("reverse x", "x from high to low (e.g. IR)"),
        ], None),
        ("Find things", 'blue', [
            ("[F1]", "Search all help pages at once"),
            ("Search…", "Next to the tool lists: type *baseline*, *smooth*, *pca*, "
                             "*melting* …"),
            ("Orange **?**", "In every window: what this part does"),
            ("Test datasets", "Help › Test datasets – try any tool"),
        ], None),
    ],
    [
        ("Right-click on the plot", 'orange', [
            ("Copy plot to clipboard", "Paste into Word / PowerPoint ([Ctrl]+[Shift]+[C])"),
            ("Save plot for publication…", "Journal column width; TIFF/PNG 300–1200 dpi, "
                                                "PDF/SVG/EPS; printing"),
            ("Copy the data in view", "Only the x range shown – a table for Excel"),
            ("Label the band here", "Also: *Add text here…*, *Add an arrow here…*, "
                                    "*Labels on the plot…* (drag them with the mouse)"),
            ("Open in New Window", "The plot in its own window"),
            ("Data table…", "The spectra as a spreadsheet; values per spectrum"),
            ("Peak list… / Detect Peaks", "Every peak of the selected spectra"),
            ("Show all spectra", "Shows spectra hidden from the legend"),
        ], None),
        ("Band markers – vertical lines at a band", 'orange', [
            ("Add", "**Cursor** ticked + click, or right-click › *Add a band marker here*"),
            ("Copy the values at the band markers",
             "Every spectrum's intensity at every marker – rows: spectra, columns: markers. "
             "Paste with [Ctrl]+[V]"),
            ("Right-click between two",
             "*Copy the values between the band markers …*: max, min, area, and the band "
             "above the line joining its ends (position, height, area, centroid)<br>"
             "*Zoom to the band markers …*: just that band"),
            ("Right-click on one", "*Scale each spectrum to 1 at the band marker …* (e.g. "
                                   "internal standard Phe 1004) · *Remove the band marker …*"),
            ("Band markers…", "All markers: name, colour, style"),
        ], None),
        ("Processing", 'blue', [
            ("Apply", "Replaces the selected spectra"),
            ("Add as New", "Keeps the originals, adds processed copies"),
            ("Undo / Redo / History", "Back to any earlier step"),
            ("Windows beside the plot", "Zoom and save the plot while a tool is open; orange "
                                        "line: *Hide / Close the window*"),
        ], None),
    ],
    [
        ("Spectra list", 'blue', [
            ("[↑] [↓]", "Step through the spectra one by one"),
            ("[Shift] / [Ctrl]+click", "Select a range / add or take out one"),
            ("[Ctrl]+[A] / [Ctrl]+[U]", "Select all / unselect all"),
            ("[Alt]+[Left] / [Alt]+[Right]", "Previous / next selection (like a browser)"),
            ("Own order", "Drag the handle **⋮⋮** at the left, or [Alt]+[Up] / [Alt]+[Down]"),
            ("Sort ▾", "Above the list: name, order added, a property (temperature, pH…), "
                            "a number in the name"),
            ("[Ctrl]+[C] / [Ctrl]+[V]", "Copy / paste copies of spectra"),
            ("[Delete] or [Ctrl]+[D]", "Delete the selected spectra"),
        ], "**Right-click on the list:** *Rename*, *Spectrum properties…* (temperature, "
           "pH, … – works like Excel: paste a block; there [Ctrl]+[D] fills down), "
           "*Plot Properties…*, *Line colours…*, *Order*, *Select spectra*."),
        ("Files", 'blue', [
            ("[Ctrl]+[I]", "Import data (instead of the current spectra)"),
            ("[Ctrl]+[Shift]+[I]", "Import data and add to the current ones"),
            ("Drag & drop", "Files from Explorer onto the window"),
            ("[Ctrl]+[Shift]+[V]", "Paste data from Excel or a text file"),
            ("[Ctrl]+[S]", "Save snapshot – your whole work (.snapx)"),
            ("[Ctrl]+[Shift]+[S]", "Save snapshot as… (a new one)"),
            ("[Ctrl]+[O]", "Open snapshot · File › Open recent"),
            ("[Ctrl]+[E]", "Export spectra: text, Excel, GRAMS (.spc)"),
        ], "A **\\*** in the window title: unsaved changes."),
        ("Every window", 'blue', [
            ("[Esc]", "Closes it (as Close / Cancel)"),
            ("[Enter]", "The highlighted button (usually OK / Apply)"),
            ("[Ctrl]+[C] in tables", "Copy cells for Excel"),
        ], None),
    ],
]

# how a key of the markup is drawn
_ARROWS = {'Up': '↑', 'Down': '↓', 'Left': '←', 'Right': '→'}


def _inline(text):
    """The markup -> HTML (text is trusted: written above; <br> kept)."""
    parts = text.split('<br>')
    out = []
    for part in parts:
        s = html.escape(part, quote=False)
        s = s.replace('\\*', '&#42;')
        s = re.sub(r'\[([^\]]+)\]', lambda m: f'<kbd>{_ARROWS.get(m.group(1), m.group(1))}</kbd>', s)
        s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
        s = re.sub(r'\*(.+?)\*', r'<i>\1</i>', s)
        out.append(s)
    return '<br>'.join(out)


def key_combinations():
    """Every key combination with Ctrl, Alt or Shift written on the page,
    e.g. 'Ctrl+Shift+C' (for the test)."""
    found = set()
    for column in COLUMNS:
        for _h, _a, rows, note in column:
            texts = [t for row in rows for t in row] + ([note] if note else [])
            for t in texts:
                for m in re.finditer(r'\[[^\]]+\](?:\+\[[^\]]+\])+', t):
                    combo = '+'.join(re.findall(r'\[([^\]]+)\]', m.group(0)))
                    if re.match(r'(Ctrl|Alt|Shift)\+', combo):
                        found.add(combo)
    return found


def get_quick_reference_help_title():
    return TITLE


def _section(heading, accent, rows, note):
    cls = ' class="o"' if accent == 'orange' else ''
    body = ''.join(f'<tr><td class="k">{_inline(k)}</td><td>{_inline(w)}</td></tr>'
                   for k, w in rows)
    note_html = f'<p class="note">{_inline(note)}</p>' if note else ''
    return f'<section><h2{cls}>{html.escape(heading)}</h2><table>{body}</table>{note_html}</section>'


def get_quick_reference_help_content():
    try:
        from src.version import __version__ as version
    except Exception:
        version = ''
    columns = ''.join('<div>' + ''.join(_section(*s) for s in column) + '</div>'
                      for column in COLUMNS)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{TITLE}</title><style>
@page {{ size: A4 landscape; margin: 9mm 10mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; color: #1d2733;
       margin: 16px; line-height: 1.35; }}
header {{ display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
         border-bottom: 2px solid #2C3E6B; padding-bottom: 3px; margin-bottom: 8px; }}
header h1 {{ font-size: 18pt; margin: 0; color: #2C3E6B; }}
header h1 span {{ color: #E65100; }}
header .sub {{ color: #55606e; }}
.print {{ background: #FFF3E0; border: 1px solid #FFCC80; border-radius: 4px; padding: 6px 10px;
          margin-bottom: 10px; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0 14px; }}
@media (max-width: 1000px) {{ .cols {{ grid-template-columns: 1fr; }} }}
section {{ break-inside: avoid; margin-bottom: 8px; }}
h2 {{ font-size: 11.5pt; color: #fff; background: #2C3E6B; margin: 0 0 3px; padding: 2px 7px;
      border-radius: 3px; }}
h2.o {{ background: #E65100; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ vertical-align: top; padding: 2px 4px; border-bottom: 1px solid #e6e9ee; }}
td.k {{ width: 38%; font-weight: 600; padding-right: 8px; }}
kbd {{ font-family: inherit; font-size: 90%; font-weight: 600; background: #f1f3f6;
       border: 1px solid #c7ccd4; border-bottom-width: 2px; border-radius: 3px; padding: 0 3px;
       white-space: nowrap; }}
.note {{ font-size: 92%; color: #55606e; margin: 2px 0 0; }}
footer {{ margin-top: 4px; border-top: 1px solid #c7ccd4; padding-top: 3px; font-size: 92%;
          color: #55606e; display: flex; justify-content: space-between; }}
a {{ color: #1565C0; }}
@media print {{
  body {{ margin: 0; font-size: 8pt; line-height: 1.27; }}
  header h1 {{ font-size: 15pt; }}
  h2 {{ font-size: 9.6pt; }}
  .print, footer {{ display: none; }}
  td.k {{ width: 36%; }}
  .cols {{ grid-template-columns: 1fr 1fr 1fr; gap: 0 12px; }}
  h2, kbd {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
}}
</style></head><body>
<header><h1>SpecAnalytiXBase <span>{version}</span> — {TITLE}</h1>
<div class="sub">Mouse, keys and right-click menus on one page</div></header>
<p class="print"><b>To print it:</b> <kbd>Ctrl</kbd>+<kbd>P</kbd> in the browser,
Layout: <b>Landscape</b> (and <i>Background graphics</i> on) &ndash; it fits one A4 page.
All keyboard shortcuts: Help &rsaquo; Keyboard shortcuts, or the
<a href="help://user_guide#keyboard">User Guide</a>.</p>
<div class="cols">{columns}</div>
<footer><span>More: <a href="help://user_guide">User Guide</a> &middot;
<a href="help://quick_start">Quick Start</a> &middot; <a href="help://whats_new">What's New</a></span>
<span>SpecAnalytiXBase {version}</span></footer>
</body></html>"""
