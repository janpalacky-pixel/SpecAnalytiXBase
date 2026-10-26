"""Spectrum properties > Fill from a file...: a table (Excel, CSV, TXT) with the
spectrum names in the first column and one column per property fills the
properties of many spectra at once; nothing is stored until Apply."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.modules.misc import spectrum_properties as sp

app = QApplication.instance() or QApplication([])


def _spectra():
    return [{'label': 'treatment : control_01', 'metadata': {}},
            {'label': 'treatment : control_02', 'metadata': {'pH': 7.0}},
            {'label': 'run 3 : high dose 1', 'metadata': {}},
            {'label': 'blank', 'metadata': {}}]


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return str(p)


# --- reading the file ----------------------------------------------------------------------

def test_text_tables_with_tab_semicolon_comma_or_spaces(tmp_path):
    tab = _write(tmp_path, 'a.txt', 'spectrum\tpH\ttemperature_C\ncontrol_01\t7.4\t25\n')
    semi = _write(tmp_path, 'b.csv', 'spectrum;pH;temperature_C\ncontrol_01;7,4;25\n')
    comma = _write(tmp_path, 'c.csv', '"spectrum","pH","temperature_C"\n"control_01",7.4,25\n')
    for path in (tab, semi, comma):
        header, rows = sp.read_table(path)
        assert header == ['spectrum', 'pH', 'temperature_C']
        assert rows == [['control_01', rows[0][1], '25']]
        assert sp.parse_value(rows[0][1]) == 7.4
    # spaces only: the name may contain spaces - everything before the values
    spaces = _write(tmp_path, 'd.txt', 'spectrum pH T\nrun 3 : high dose 1   6.5  40\n')
    header, rows = sp.read_table(spaces)
    assert rows == [['run 3 : high dose 1', '6.5', '40']]


def test_excel_uses_the_sheet_properties_or_the_first(tmp_path):
    import pandas as pd
    path = str(tmp_path / 'props.xlsx')
    with pd.ExcelWriter(path) as w:
        pd.DataFrame({'a': [1]}).to_excel(w, sheet_name='Notes', index=False)
        pd.DataFrame({'spectrum': ['control_01', 'control_02'], 'pH': [7.4, 8.0],
                      'conc (mM)': [1.5, None]}).to_excel(w, sheet_name='Properties', index=False)
    header, rows = sp.read_table(path)
    assert header == ['spectrum', 'pH', 'conc (mM)']
    assert rows[0][0] == 'control_01' and float(rows[1][1]) == 8.0 and rows[1][2] == ''


def test_a_file_without_property_columns_is_refused(tmp_path):
    with pytest.raises(ValueError):
        sp.read_table(_write(tmp_path, 'e.txt', 'only_names\ncontrol_01\n'))


# --- what the table gives the spectra ------------------------------------------------------

def test_names_matched_in_full_as_in_the_data_file_and_loosely():
    header = ['Spectrum', 'pH', 'Temperature (°C)', 'note']
    rows = [['control_01', '7,4', '25', 'fine'],       # the part after ' : '
            ['TREATMENT : CONTROL_02', '', '30', ''],  # full name, other case; pH empty
            ['run_3_high_dose_1', 'n.d.', '35', ''],   # punctuation ignored; pH not a number
            ['ghost', '1', '2', '']]                   # no such spectrum
    r = sp.from_table(_spectra(), header, rows)
    assert r['keys'] == ['pH', 'Temperature_C']              # the notes column left out
    assert r['values']['pH'] == [7.4, None, None, None]       # None = not changed
    assert r['values']['Temperature_C'] == [25.0, 30.0, 35.0, None]
    assert r['found'] == 3 and r['not_found'] == ['blank'] and r['unused'] == ['ghost']
    assert r['bad_cells'] == [('run_3_high_dose_1', 'pH', 'n.d.')]
    assert r['skipped'] == [('note', 'no numbers (properties must be numbers)')]
    report = sp.table_report(r)
    assert 'Found: 3 of 4 spectra.' in report and 'ghost' in report and 'n.d.' in report


def test_column_names_become_property_names():
    assert sp.make_name('Temperature (°C)') == 'Temperature_C'
    assert sp.make_name('2nd run') == 'p_2nd_run'
    assert sp.make_name('  ', 3) == 'property_3'
    spectra = [{'label': 'a', 'metadata': {'file': 'x.txt'}}]
    r = sp.from_table(spectra, ['name', 'file', 'pH', 'p H', 'p-H'], [['a', '1', '2', '3', '4']])
    assert r['keys'] == ['pH', 'p_H']                        # 'p H' -> p_H
    assert r['skipped'][0][0] == 'file' and 'as text' in r['skipped'][0][1]   # used by the program
    assert r['skipped'][1][0] == 'p-H' and 'same name' in r['skipped'][1][1]  # p_H again


def test_nothing_found_explains_the_first_column():
    r = sp.from_table(_spectra(), ['x', 'pH'], [['zzz', '1']])
    assert r['found'] == 0 and 'first column must hold the spectrum names' in sp.table_report(r)


# --- the window ----------------------------------------------------------------------------

def test_the_window_fills_new_and_existing_columns_until_apply(tmp_path, monkeypatch):
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    shown = []
    monkeypatch.setattr(QMessageBox, 'information', staticmethod(lambda *a, **k: shown.append(a[2])))
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: shown.append(a[2])))
    path = _write(tmp_path, 'p.csv', 'spectrum;pH;temperature_C\ncontrol_01;7,4;25\n'
                                     'control_02;;30\n')
    stored = []
    win = SpectrumPropertiesDialog(None, _spectra(),
                                   apply_callback=lambda s, v: (stored.append(v) or True, 'ok'))
    assert win.keys == ['pH']
    result = win.fill_from_file(path)
    assert result['found'] == 2 and win.keys == ['pH', 'temperature_C']
    values, problems = win.values()
    assert not problems
    assert [v['pH'] for v in values] == [7.4, 7.0, None, None]      # 7.0 kept (empty cell)
    assert [v['temperature_C'] for v in values] == [25.0, 30.0, None, None]
    assert 'Found: 2 of 4 spectra.' in shown[-1] and 'Apply stores them' in shown[-1]
    assert win.apply_button.isEnabled() and not stored               # not stored yet
    assert win.apply() and stored


def test_the_button_asks_for_the_file_and_a_bad_file_only_warns(tmp_path, monkeypatch):
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    asked, warned = [], []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                        staticmethod(lambda *a, **k: asked.append(1) or ('', '')))
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: warned.append(a[2])))
    win = SpectrumPropertiesDialog(None, _spectra())
    win.file_button.click()
    assert asked == [1] and not warned                   # cancelled: nothing happens
    assert win.fill_from_file(_write(tmp_path, 'bad.txt', 'just one line\n')) is None
    assert 'could not be read' in warned[-1]


# --- when it is not clear, nothing is filled -------------------------------------------------

def test_a_name_twice_in_the_table_is_left_out():
    spectra = [{'label': 'demo : control_01', 'metadata': {}},
               {'label': 'demo : control_02', 'metadata': {}}]
    rows = [['control_01', '7.4'], ['Control 01', '8.0'], ['control_02', '7.0']]
    r = sp.from_table(spectra, ['spectrum', 'pH'], rows)
    assert r['values']['pH'] == [None, 7.0]                # which pH of control_01 is right?
    assert r['twice'] == ['control_01', 'Control 01'] and r['not_found'] == []
    assert 'row “control_01” – it is in the table twice; which one is right?' in sp.table_report(r)
    assert 'control_01' not in r['unused']


def test_a_short_name_of_several_spectra_is_left_out_full_names_work():
    spectra = [{'label': 'day1 : control_01', 'metadata': {}},
               {'label': 'day2 : control_01', 'metadata': {}},
               {'label': 'day2 : control_02', 'metadata': {}}]
    r = sp.from_table(spectra, ['spectrum', 'pH'], [['control_01', '7.4'], ['control_02', '7.0']])
    assert r['values']['pH'] == [None, None, 7.0]
    assert r['unclear'] == [('control_01', ['day1 : control_01', 'day2 : control_01'])]
    assert r['not_found'] == [] and r['unused'] == [] and r['found'] == 1
    report = sp.table_report(r)
    assert 'Found: 1 of 3 spectra.' in report
    assert ('row “control_01” fits 2 spectra, e.g. “control_01” fits “day1 : control_01” and '
            '“day2 : control_01”.') in report
    assert 'Write the full names, as in the spectra list, in the table.' in report
    r = sp.from_table(spectra, ['spectrum', 'pH'],
                      [['day1 : control_01', '7.4'], ['day2 : control_01', '8.0']])
    assert r['values']['pH'] == [7.4, 8.0, None] and not r['unclear']


def test_the_full_name_comes_before_the_short_name_and_the_original_name_counts():
    spectra = [{'label': 'control_01', 'metadata': {}},                 # full name
               {'label': 'day1 : control_01', 'metadata': {}},          # short name only
               {'label': 'renamed', 'metadata': {'original_label': 'run : sample_7'}}]
    r = sp.from_table(spectra, ['spectrum', 'pH'], [['control_01', '7.4'], ['sample_7', '6.0']])
    assert r['values']['pH'] == [7.4, None, 6.0] and not r['unclear']
    assert r['not_found'] == ['day1 : control_01']


def test_the_example_table_of_the_help(tmp_path, monkeypatch):
    """The example (resources/test_data/examples) fits the test dataset
    'Group Statistics - three treatment groups'; the help saves a copy."""
    import os
    from src.views.dialogs.misc.spectrum_properties_dialog import SpectrumPropertiesDialog
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.chdir(root)                                   # resource_path (not installed)
    spectra = [{'label': f'group_stats_treatment_demo : {g}_{i:02d}', 'metadata': {}}
               for g in ('control', 'low_dose', 'high_dose') for i in range(1, 13)]
    for ext in ('.xlsx', '.csv'):
        header, rows = sp.read_table(os.path.join(root, SpectrumPropertiesDialog.EXAMPLE + ext))
        r = sp.from_table(spectra, header, rows)
        assert r['found'] == 36 and r['keys'] == ['dose_mg_L', 'Temperature_C']
        assert r['unused'] == ['ghost_99'] and r['bad_cells'][0][2] == 'n.d.'
        assert r['skipped'] == [('note', 'no numbers (properties must be numbers)')]
    win = SpectrumPropertiesDialog(None, spectra)
    target = str(tmp_path / 'my_copy.xlsx')
    assert win.example_link('example:save', target) == target and os.path.getsize(target) > 0
    assert win.example_link('example:save-csv', str(tmp_path / 'c.csv')).endswith('c.csv')
    assert 'example:save' in win.show_help().findChild(
        __import__('PyQt5.QtWidgets', fromlist=['QTextBrowser']).QTextBrowser).toHtml()


def test_the_message_of_the_example_says_what_was_filled_and_what_not():
    spectra = [{'label': f'group_stats_treatment_demo : {g}_{i:02d}', 'metadata': {}}
               for g in ('control', 'low_dose', 'high_dose') for i in range(1, 13)]
    root = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
    header, rows = sp.read_table(root + '/resources/test_data/examples/treatment_properties.xlsx')
    assert sp.table_report(sp.from_table(spectra, header, rows)).splitlines() == [
        'Found: 36 of 36 spectra.',
        'Filled: dose_mg_L (column “dose (mg/L)”), Temperature_C (column “Temperature (°C)”).',
        'Not used:',
        ' • row “ghost_99” – no spectrum has this name',
        ' • control_04, “dose (mg/L)”: “n.d.” is not a number – control_04 gets no dose_mg_L',
        ' • column “note” – no numbers (properties must be numbers)']
    # one number in the column of notes: it is a property; the text cells are listed together
    rows[0][3] = '55'
    r = sp.from_table(spectra, header, rows)
    assert r['keys'] == ['dose_mg_L', 'Temperature_C', 'note']
    assert (' • column “note”: 35 cells are not numbers (e.g. “ok” for control_02) – those '
            'spectra get no note') in sp.table_report(r).splitlines()
    # the same data file twice: one line for all names that fit several spectra
    twice = spectra + [dict(s, label=s['label'] + ' (2)',
                            metadata={'original_label': s['label']}) for s in spectra]
    lines = sp.table_report(sp.from_table(twice, header, rows)).splitlines()
    assert lines[0] == 'Found: 0 of 72 spectra – nothing filled.'
    assert lines[2].startswith(' • 36 names fit several spectra each, e.g. “control_01” fits '
                               '“group_stats_treatment_demo : control_01” and')
