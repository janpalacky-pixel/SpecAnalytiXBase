"""Conveniences: the vertical cursor of the main plot, pasting numbers from
Excel / text as spectra, opening files given on the command line, and the
dark theme's colour conversion."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_io.clipboard_table import ClipboardTableError, parse_table
from src.modules.visualization import cursor_values as cv

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA = os.path.join(ROOT, 'resources', 'test_data', 'real', 'Raman_DNA_conc_dep.txt')


def _pump(seconds=0.2):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


# --- cursor values (Qt-free) ------------------------------------------------------------

def test_values_are_interpolated_never_extrapolated():
    x, y = np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 40.0])
    assert cv.value_at(x, y, 2.5) == 30.0
    assert cv.value_at(x[::-1], y[::-1], 1.5) == 15.0          # decreasing x works
    assert cv.value_at(x, y, 0.5) is None and cv.value_at(x, y, 3.5) is None
    vals = cv.values_at([('a', x, y), ('b', x + 10, y)], 2.0)
    assert vals == [('a', 20.0)]


def test_listed_values_nearest_to_the_pointer_and_table():
    vals = [(f's{i}', float(i)) for i in range(15)]
    shown, hidden = cv.listed(vals, pointer_y=7.2, limit=4)
    assert hidden == 11 and [l for l, _ in shown] == ['s9', 's8', 's7', 's6']
    x = np.array([1.0, 2.0, 3.0])
    table = cv.table_text([('a', x, x * 2), ('b', x + 5, x)], [1.5, 2.0])
    lines = table.rstrip('\n').split('\n')
    assert lines[0] == 'Spectrum\tx = 1.5\tx = 2'
    assert lines[1] == 'a\t3.0\t4.0' and lines[2] == 'b\t\t'
    assert cv.fmt(270234.4) == '270234' and cv.fmt(1.2e-5) == '1.2e-05' and cv.fmt(None) == '—'


# --- clipboard table (Qt-free) -------------------------------------------------------------

def test_excel_with_header_and_decimal_comma():
    x_name, spectra, notes = parse_table('nm\tA\tB\n200\t0,1\t0,2\n201\t0,15\t\n202\t0,2\t0,3\n')
    assert x_name == 'nm' and [s[0] for s in spectra] == ['A', 'B']
    assert np.allclose(spectra[0][2], [0.1, 0.15, 0.2])
    assert np.allclose(spectra[1][1], [200, 202])               # empty cell: no point
    assert notes == ["The table was read in columns: x = the first column, one spectrum per "
                     "further column, names from the header row."]


@pytest.mark.parametrize('text, names, first_y', [
    ('200 1 2\n201 3 4\n202 5 6', ['column 2', 'column 3'], [1, 3, 5]),
    ('x,a\n1,2.5\n2,3.5\n3,4', ['a'], [2.5, 3.5, 4]),
    ('200;1,5\n201;2,5\n202;3', ['column 2'], [1.5, 2.5, 3]),
    ('\t200\t201\t202\ns1\t1\t2\t3\ns2\t4\t5\t6', ['s1', 's2'], [1, 2, 3]),
    ('5\n6\n7', ['column 1'], [5, 6, 7]),
])
def test_other_table_shapes(text, names, first_y):
    _, spectra, _ = parse_table(text)
    assert [s[0] for s in spectra] == names
    assert np.allclose(spectra[0][2], first_y)


def test_rows_with_names_and_x_in_the_header_row():
    """E.g. a Specord export with only the Name column and the numbers
    copied (and a separator at the end of every line)."""
    text = ('Name;230,0;231,0;232,0;\n'
            'rC5U3;0,1460;0,1351;0,1300;\n'
            'rC5U3;0,2;0,3;0,4;\n'
            'blank;0,01;0,02;0,03;\n')
    x_name, spectra, notes = parse_table(text)
    assert x_name == 'Name' and [s[0] for s in spectra] == ['rC5U3', 'rC5U3 (2)', 'blank']
    assert np.allclose(spectra[0][1], [230, 231, 232]) and np.allclose(spectra[0][2], [0.146, 0.1351, 0.13])
    assert 'x = the header row' in notes[0]
    # the same numbers without names: first row = x
    _, spectra, notes = parse_table('230\t231\t232\n0,1\t0,2\t0,3\n0,4\t0,5\t0,6')
    assert len(spectra) == 2 and np.allclose(spectra[1][2], [0.4, 0.5, 0.6])
    assert 'first row = x' in notes[0]


def test_rows_with_several_leading_columns_as_exported_by_a_spectrometer():
    """dev_notes/multiple_column_header-ii.txt: No., Type, Name, Date, Note,
    Temperature (decimal comma) ... then the absorbances (decimal point)."""
    text = ('user\tNo.\tType\tName\tDate/Time\tNote\tTemperature\tTemperature\t230.0000\t231.0000\t232.0000\r\n'
            'A\t1.0000\tSample\trC5U3\t2021.06.21 12:28\t\t4,1\t4,0\t0.1460\t0.1351\t0.1272\r\n'
            'b\t2.0000\tSample\trC3,5\t2021.06.21 12:28\t\t4,1\t4,0\t0.5664\t0.5424\t0.5237\r\n'
            'D\t5.0000\tSample\trC5U3\t2021.06.21 12:33\t\t4,8\t5,0\t0.1612\t0.1530\t0.1451\r\n')
    x_name, spectra, notes = parse_table(text)
    assert [s[0] for s in spectra] == ['rC5U3', 'rC3,5', 'rC5U3 (2)']
    assert np.allclose(spectra[0][1], [230, 231, 232]) and np.allclose(spectra[1][2], [0.5664, 0.5424, 0.5237])
    assert 'column 9' in notes[0] and '7 leading columns' in notes[0]


def test_rows_message_names_the_x_range_and_the_left_out_columns_briefly():
    """The message after pasting a spectrometer export says which x-values were
    found and which leading columns were left out, by name -- at most 8 names,
    each cut to 20 characters, so the window stays small."""
    text = ('No.;Type;Name;Date/Time;Note;Temperature;Temperature;230,0;231,0;232,0\n'
            '1;Sample;rC5U3;2021.06.21 12:28;;4,1;4,0;0,1460;0,1351;0,1272\n'
            '2;Sample;rC3,5;2021.06.21 12:28;;4,1;4,0;0,5664;0,5424;0,5237\n')
    _, _, notes = parse_table(text)
    assert notes == ['The table was read in rows: x = the header row from column 8 on (230 \u2026 232), '
                     'names from the column \u201cName\u201d; the other 6 leading columns were left out: '
                     'No., Type, Date/Time, Note, Temperature, Temperature.']
    header = '\t'.join(['Name'] + [f'a very long column name {i}' for i in range(15)] + ['230', '231', '232'])
    rows = ['\t'.join([f's{r}'] + ['x'] * 15 + ['1', '2', '3']) for r in range(2)]
    _, _, notes = parse_table('\n'.join([header] + rows))
    assert notes[0].count('\u2026,') == 7 and notes[0].endswith('\u2026 and 7 more.')
    assert 'a very long column \u2026' in notes[0] and len(notes[0]) < 400


def test_every_paste_says_whether_it_read_columns_or_rows():
    """The message after a paste always names the layout, so a wrong guess
    is noticed: columns without a header row too."""
    for text, words in (('200 1 2\n201 3 4\n202 5 6', 'read in columns'),
                        ('x,a\n1,2.5\n2,3.5\n3,4', 'names from the header row'),
                        ('230\t231\t232\n0,1\t0,2\t0,3\n0,4\t0,5\t0,6', 'read in rows'),
                        ('5\n6\n7', 'One column only')):
        _, _, notes = parse_table(text)
        assert len(notes) == 1 and words in notes[0], (text, notes)
    _, _, notes = parse_table('200 1 2\n201 3 4\n202 5 6')
    assert 'header' not in notes[0]


def test_decreasing_x_is_stored_increasing_and_errors_are_plain():
    _, spectra, _ = parse_table('210\t1\n205\t2\n200\t3')
    assert np.allclose(spectra[0][1], [200, 205, 210]) and np.allclose(spectra[0][2], [3, 2, 1])
    for bad, words in (('', 'empty'), ('hello\nworld', 'Not a table'),
                       ('1\t2\n1\t3\n1\t4', 'not increasing')):
        with pytest.raises(ClipboardTableError) as e:
            parse_table(bad)
        assert words in str(e.value)


# --- the main window -----------------------------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    seen = []
    for n in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, n, staticmethod(
            lambda *a, **k: seen.append(a[2] if len(a) > 2 else '') or QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, 'question', staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, 'exec_', lambda self: QMessageBox.Yes)
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths or [DATA]),
                                                 [{} for _ in (file_paths or [DATA])])))
    from src.controllers.core.main_controller import MainController
    ctrl = MainController()
    ctrl.messages = seen
    yield ctrl
    ctrl.autosave_controller.shutdown()
    ctrl.view.deleteLater()


def _labels(mc):
    return [mc.spectra_list_widget.item(i).text() for i in range(mc.spectra_list_widget.count())]


def test_paste_into_an_empty_and_into_a_loaded_workspace(mc):
    assert mc.paste_data_from_clipboard('nm\tA\tB\n200\t1\t2\n201\t3\t4\n202\t5\t6') == 2
    assert _labels(mc) == ['Pasted 1 : A', 'Pasted 1 : B']
    mc.import_controller._run_import(clear_first=False, file_paths=[DATA])
    _pump()
    n = len(_labels(mc))
    om = mc.operations_controller.operations_manager
    steps = len(om.operations_chain)
    assert mc.paste_data_from_clipboard('x;y\n1;2\n2;3\n3;5') == 1
    assert len(_labels(mc)) == n + 1 and 'Pasted 2 : y' in _labels(mc)
    assert om.operations_chain[-1]['type'] == 'Import' and len(om.operations_chain) == steps + 1
    pasted = [s for s in mc.original_spectra if s['label'] == 'Pasted 2 : y'][0]
    assert pasted['metadata']['source'] == 'clipboard'
    assert mc.paste_data_from_clipboard('just words') == 0      # explained, nothing added
    assert mc.messages and 'Copy a block of numbers' in mc.messages[-1]


def test_ctrl_v_still_pastes_copies_of_spectra(mc):
    """Numbers are pasted with Ctrl+Shift+V; Ctrl+V on the list stays the
    copy / paste of spectra, whatever the clipboard holds."""
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump()
    n = len(_labels(mc))
    mc.copy_spectra_to_clipboard()
    QApplication.clipboard().setText('x\ty\n1\t2\n2\t3\n3\t4')
    mc.paste_spectra_from_clipboard()
    _pump()
    assert len(_labels(mc)) == 2 * n and not any(l.startswith('Pasted') for l in _labels(mc))
    assert mc.paste_data_action.shortcut().toString() == 'Ctrl+Shift+V'
    mc.paste_data_action.trigger()
    _pump()
    assert 'Pasted 1 : y' in _labels(mc)


def test_open_paths_from_the_command_line(mc, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(mc.import_controller, 'open_snapshot_path', lambda p: opened.append(p))
    mc.open_paths([DATA, str(tmp_path / 'nothing.txt'), str(tmp_path / 'a.snapx')])
    _pump()
    assert any('nothing.txt' in m for m in mc.messages)          # missing file named
    assert len(_labels(mc)) > 0                                   # the data file imported
    snap = tmp_path / 'b.snapx'
    snap.write_bytes(b'x')
    mc.open_paths([str(snap)])
    assert opened == [str(snap)]


def test_main_passes_only_file_arguments():
    sys.path.insert(0, ROOT)
    import main
    assert main._file_arguments(['a.txt', '--multiprocessing-fork', '', 'b.snapx']) == \
        ['a.txt', 'b.snapx']


def test_cursor_lists_values_and_copies_pinned_ones(mc):
    mc.view.resize(1400, 900)
    mc.view.show()
    mc.import_controller._run_import(clear_first=True, file_paths=[DATA])
    _pump()
    mc.spectrum_selector.select_all_items()
    _pump(0.5)
    cc = mc.plot_cursor_controller
    assert cc.canvas is mc.static_canvas
    mc.cursor_checkbox.setChecked(True)
    assert cc.enabled
    ax = mc.static_canvas.figure.axes[0]
    text, shown = cc.readout_text(ax, 1000.0, None)
    assert text.startswith('x = 1000') and len(shown) == 10 and '+ 1 more' in text
    curves = cc.all_curves()
    assert len(curves) == 11
    by_label = {lbl: (xx, yy) for lbl, xx, yy in curves}
    for lbl, v in shown:
        xx, yy = by_label[lbl]
        assert v == pytest.approx(np.interp(1000.0, xx, yy))
    # a mouse move draws the live cursor without an error
    from matplotlib.backend_bases import MouseEvent
    mc.static_canvas.draw()
    px, py = ax.transData.transform((1200.0, np.mean(ax.get_ylim())))
    mc.static_canvas.callbacks.process('motion_notify_event',
                                       MouseEvent('motion_notify_event', mc.static_canvas, px, py))
    cc.pin(800.0)
    cc.pin(1500.0)
    assert cc.copy_table() == 11
    rows = QApplication.clipboard().text().strip().split('\n')
    assert rows[0] == 'Spectrum\tx = 800\tx = 1500' and len(rows) == 12
    mc.plot_spectra()                                   # pinned cursors stay
    _pump()
    assert mc.plot_cursor_controller.pinned == [800.0, 1500.0]
    cc.clear_pinned()
    assert cc.pinned == []


# --- dark theme -------------------------------------------------------------------------------

def test_dark_colours_keep_hue_and_invert_lightness():
    from src.views.theme import convert_css, dark_hex
    assert dark_hex('#FFFFFF') == '#1f1f1f'                       # white background -> dark
    assert dark_hex('#000000') == '#ebebeb'                       # black text -> light
    out = convert_css('QPushButton { background-color: #3A6AAF; color: white; '
                      'border: 1px solid #B0B8C8; white-space: pre }')
    assert 'color: #ffffff' in out                                # white text on a button stays
    assert '#3a6aaf' not in out.lower() and 'white-space' in out
    html = convert_css("<span style='color:#1A1A2E'>a</span> <font color=\"#2E7D32\">b</font>")
    assert '#1a1a2e' not in html.lower() and '#2e7d32' not in html.lower()


def test_theme_menu_and_preference(mc):
    from src.views import theme
    assert theme.saved_theme() == 'light'
    assert set(mc.theme_actions) == {'light', 'dark'} and mc.theme_actions['light'].isChecked()
    mc.theme_actions['dark'].trigger()
    assert theme.saved_theme() == 'dark'
    assert any('next start' in m for m in mc.messages)
