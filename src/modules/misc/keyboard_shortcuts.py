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
    ('Spectra list', 'Ctrl+A', 'Select all spectra'),
    ('Spectra list', 'Ctrl+U', 'Unselect all spectra'),
    ('Spectra list', 'Ctrl+C', 'Copy the selected spectra (remembered for Ctrl+V)'),
    ('Spectra list', 'Ctrl+V', 'Paste copies of the copied spectra'),
    ('Spectra list', 'Ctrl+D', 'Delete the selected spectra'),
    ('Spectra list', 'Delete', 'Delete the selected spectra'),
    ('Spectra list', 'Shift+click', 'Select from the last clicked spectrum to this one'),
    ('Spectra list', 'Ctrl+click', 'Add a spectrum to the selection, or take it out'),
    ('Tables in tool windows', 'Ctrl+C', 'Copy the selected cells (e.g. into Excel)'),
    ('Tables in tool windows', 'Ctrl+X', 'Cut the selected cells (tables you can edit)'),
    ('Tables in tool windows', 'Ctrl+V', 'Paste cells, e.g. from Excel (tables you can edit)'),
    ('Tables in tool windows', 'Delete', 'Clear the selected cells (tables you can edit)'),
    ('Group Statistics: group table', 'Ctrl+D', 'Fill down: the first selected value into the cells below'),
    ('Group Statistics: group table', 'Ctrl+Z', 'Undo the last change of the table'),
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
