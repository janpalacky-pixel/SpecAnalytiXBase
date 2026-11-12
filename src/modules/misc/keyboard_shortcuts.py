# src/modules/misc/keyboard_shortcuts.py
"""Every keyboard shortcut of SpecAnalytiXBase in one list (Qt-free). Shown
by Help -> Keyboard shortcuts... and in the User Guide (section "Keyboard
Shortcuts", the table is filled from here), so both always agree.
tests/test_keyboard_shortcuts.py checks that every shortcut of the main
window is listed here and that every main-window shortcut listed here exists.
A new shortcut goes into this list."""

from html import escape

# (where, keys, what it does). 'Main window' and 'Spectra list' rows are
# checked against the program by the test; the others describe tool windows.
SHORTCUTS = [
    ('Main window', 'Ctrl+I', 'Import data: new (instead of the current spectra)'),
    ('Main window', 'Ctrl+Shift+I', 'Import data: add to the current spectra'),
    ('Main window', 'Ctrl+O', 'Open snapshot'),
    ('Main window', 'Ctrl+S', 'Save (selected spectra or a snapshot)'),
    ('Main window', 'Ctrl+Shift+V', 'Paste data from the clipboard (numbers from Excel or a text file)'),
    ('Main window', 'Ctrl+Shift+C', 'Copy the plot as a picture (to paste into Word, PowerPoint, e-mail)'),
    ('Main window', 'F1', 'Search the help: a word in all help pages at once'),
    ('Spectra list', 'Ctrl+A', 'Select all spectra'),
    ('Spectra list', 'Ctrl+U', 'Unselect all spectra'),
    ('Spectra list', 'Ctrl+C', 'Copy the selected spectra (remembered for Ctrl+V)'),
    ('Spectra list', 'Ctrl+V', 'Paste copies of the copied spectra'),
    ('Spectra list', 'Ctrl+D', 'Delete the selected spectra'),
    ('Spectra list', 'Delete', 'Delete the selected spectra'),
    ('Spectra list', 'Shift+click', 'Select from the last clicked spectrum to this one'),
    ('Spectra list', 'Ctrl+click', 'Add a spectrum to the selection, or take it out'),
    ('Spectra list', 'Alt+Up', 'Move the selected spectra one place up (your own order)'),
    ('Spectra list', 'Alt+Down', 'Move the selected spectra one place down'),
    ('Spectra list', 'Alt+Left', 'The previous selection (e.g. before new spectra were selected)'),
    ('Spectra list', 'Alt+Right', 'The next selection (after Alt+Left)'),
    ('Tables in tool windows', 'Ctrl+C', 'Copy the selected cells (e.g. into Excel)'),
    ('Tables in tool windows', 'Ctrl+X', 'Cut the selected cells (tables you can edit)'),
    ('Tables in tool windows', 'Ctrl+V', 'Paste cells, e.g. from Excel (tables you can edit)'),
    ('Tables in tool windows', 'Delete', 'Clear the selected cells (tables you can edit)'),
    ('Group Statistics: group table', 'Ctrl+D', 'Fill down: the first selected value into the cells below'),
    ('Group Statistics: group table', 'Ctrl+Z', 'Undo the last change of the table'),
    ('Peak Fitting (several spectra)', 'Alt+Left / Alt+Right',
     'The previous / next spectrum; with several selected, the orange frame moves among them'),
    ('Peak Fitting (several spectra)', 'Alt+Up / Alt+Down',
     'The same (as up and down in the list); both work wherever the focus is'),
    ('Plot', 'Mouse wheel', 'Zoom x around the mouse: forward (away from you) in, back out; Home: the start'),
    ('Plot', 'Ctrl+mouse wheel', 'The same for the y axis (the x axis stays)'),
    ('Plot', 'Left button held + move the mouse', 'Move (pan) the plot; Back: one step back, Home: the start'),
    ('Plot', 'Click a line', 'Its spectrum in the list: the row in bold, framed, scrolled into view'),
    ('Plot', 'Click a name in the legend', 'Hide that spectrum (in every plot type); click again to show it'),
    ('Plot', 'Right-click > Show all spectra', 'Show the hidden spectra again'),
    ('Plots in tool windows', 'Mouse wheel / Ctrl+mouse wheel',
     'Zoom x / y around the mouse, as in the main plot; Home: the start'),
    ('Plots in tool windows', 'Left button held + move the mouse',
     'Move (pan) the plot - not where a click or a drag already does something there '
     '(adds a point, draws a range)'),
    ('Plot', 'Esc', 'End Zoom / Pan of the toolbar; pressed again: the Cursor off '
     '(no more band markers with a click)'),
    ('Plots in tool windows', 'Esc', 'End Zoom / Pan of the toolbar (the window stays open)'),
    ('Plot (your labels)', 'Delete', 'Delete the chosen label (a click on it chooses it)'),
    ('Save plot for publication', 'Ctrl+Z', 'Undo: the last change in the window'),
    ('Save plot for publication', 'Ctrl+Y', 'Redo: the undone change again'),
    ('Save plot for publication', 'Delete', 'Delete the label chosen in the preview'),
    ('Data table', 'Ctrl+C', 'Copy the selected cells with their column names'),
    ('Data table', 'Enter', 'In the formula: add the column'),
    ('Every window', 'Esc', 'Close the window (as Close or Cancel)'),
    ('Every window', 'Enter', 'The highlighted button (usually OK or Apply)'),
]

GROUPS_CHECKED = ('Main window', 'Spectra list')


def groups():
    """[(where, [(keys, what), ...])] in the order of the list."""
    out = []
    for where, keys, what in SHORTCUTS:
        if not out or out[-1][0] != where:
            out.append((where, []))
        out[-1][1].append((keys, what))
    return out


def html_table():
    """The table for the User Guide and the Keyboard shortcuts window."""
    rows = ['<table><tr><th>Shortcut</th><th>What it does</th></tr>']
    for where, items in groups():
        rows.append(f'<tr><td colspan="2"><b>{escape(where)}</b></td></tr>')
        for keys, what in items:
            rows.append(f'<tr><td><span class="kbd">{escape(keys)}</span></td>'
                        f'<td>{escape(what)}</td></tr>')
    rows.append('</table>')
    return '\n'.join(rows)
