"""Data table: a range beyond the spectra is narrowed to where they have
data; a column sent again replaces its old one; the columns are made again
the next time the Data table opens; each tab has a short line and an orange
"?" (no text above the tabs)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QLabel

from src.modules.data_analysis.value_table import ValueTable

app = QApplication.instance() or QApplication([])


def _cd(labels=('cd_10C', 'cd_20C', 'cd_30C')):
    """CD spectra measured from 220 to 480 nm, a band at 222 nm."""
    x = np.linspace(220, 480, 261)
    return [{'label': lab, 'x_scale': x, 'y_scale': (k + 1) * np.exp(-((x - 222) / 8) ** 2),
             'metadata': {'temperature_C': 10.0 * (k + 1)}} for k, lab in enumerate(labels)]


def test_a_range_beyond_the_spectra_is_narrowed():
    t = ValueTable.from_spectra(_cd())
    col = t.add_value({'kind': 'max', 'range_a': (215, 225)})
    assert np.all(np.isfinite(col.values))                           # before: no values at all
    assert col.title == 'Maximum over 220–225'
    assert 'narrowed to 220–225' in col.note and 'from 220 to 480' in col.note
    assert col.asked['range_a'] == (215, 225)                        # remembered as chosen
    wide = t.add_value({'kind': 'area', 'range_a': (210, 330)})
    assert wide.title == 'Area over 220–330' and np.all(np.isfinite(wide.values))
    inside = t.add_value({'kind': 'area', 'range_a': (230, 330)})
    assert inside.note == '' and inside.title == 'Area over 230–330'
    out = t.add_value({'kind': 'area', 'range_a': (100, 200)})
    assert 'outside' in out.note and np.all(np.isnan(out.values))
    two = t.add_value({'kind': 'ratio', 'range_a': (200, 240), 'range_b': (300, 500)})
    assert two.note.count('narrowed') == 2 and np.all(np.isfinite(two.values))


def test_a_shorter_spectrum_does_not_narrow_the_range_of_the_others():
    sp = _cd()
    x = np.linspace(300, 480, 181)
    sp.append({'label': 'short', 'x_scale': x, 'y_scale': np.ones_like(x), 'metadata': {}})
    t = ValueTable.from_spectra(sp)
    col = t.add_value({'kind': 'max', 'range_a': (215, 225)})
    assert col.title == 'Maximum over 220–225'
    assert np.all(np.isfinite(col.values[:3])) and np.isnan(col.values[3])


def test_the_panel_says_that_the_range_was_narrowed():
    from src.views.dialogs.data_analysis.value_table_panel import ValueTablePanel
    panel = ValueTablePanel(None, _cd())
    panel.add_value({'kind': 'max', 'range_a': (215, 225)})
    assert 'narrowed to 220–225' in panel.message.text()
    assert 'B45309' in panel.message.styleSheet()                   # orange: a note, not an error


def test_a_column_sent_again_gets_the_new_numbers():
    t = ValueTable.from_spectra(_cd())
    first = t.add_bands('Height (y)', [('222', [1, 2, 3])])[0]
    again = t.add_bands('Height (y)', [('222', [4, 5, 6])])[0]
    assert again is first and first.name == 'b1' and list(first.values) == [4, 5, 6]
    assert [c.name for c in t.columns if c.kind == 'band'] == ['b1']


def test_a_formula_follows_new_numbers_of_its_column():
    t = ValueTable.from_spectra(_cd())
    t.add_bands('Height (y)', [('222', [1, 2, 3])])
    t.add_formula('b1 * 2')
    t.add_formula('f1 + 1')
    t.add_bands('Height (y)', [('222', [10, 20, None])])            # the Peak list sent again
    assert list(t.column('f1').values[:2]) == [20, 40] and np.isnan(t.column('f1').values[2])
    assert list(t.column('f2').values[:2]) == [21, 41]


def test_a_band_whose_position_moved_fills_its_own_column():
    """Prominence lowered in the Peak list: the band at 400.5 (3 spectra) is
    now found in all of them, at 403; a new band at 222 appears; the band at
    350 is gone."""
    t = ValueTable.from_spectra(_cd())
    t.add_bands('Height (y)', [('288', [24, 24, 24]), ('400.5', [8, 7, None]),
                               ('350', [1, 1, 1])])
    t.add_formula('b2 * 2')
    t.add_bands('FWHM', [('288', [5, 5, 5])])                         # another value: kept
    cols = t.add_bands('Height (y)', [('222', [None, 3, 4]), ('288', [24, 24, 24]),
                                      ('403', [8, 7, 6])], tolerance=16)
    assert [c.name for c in cols] == ['b5', 'b1', 'b2']             # 222 is new
    assert t.column('b2').title == 'Height of the band at 403'
    assert list(t.column('b2').values) == [8, 7, 6]
    assert list(t.column('f1').values) == [16, 14, 12]               # the formula follows
    assert t.column('b3') is None and t.removed_bands == ['b3']     # 350 is gone
    assert t.column('b4').title == 'FWHM of the band at 288'
    # without the tolerance only the same position counts
    t2 = ValueTable.from_spectra(_cd())
    t2.add_bands('Height (y)', [('400.5', [8, 7, None])])
    assert t2.add_bands('Height (y)', [('403', [8, 7, 6])])[0].name == 'b2'


def test_the_columns_are_made_again_for_other_spectra():
    t = ValueTable.from_spectra(_cd())
    t.add_bands('Height (y)', [('222', [1, 2, None])])
    t.add_value({'kind': 'max', 'range_a': (215, 225)})
    t.add_formula('v1 / max_val(v1)', 'scaled')
    t.add_formula('b1 * 2')
    recipes = t.recipes()
    assert [r['name'] for r in recipes] == ['b1', 'v1', 'f1', 'f2']
    # the same spectra: everything again, under the same names
    same = ValueTable.from_spectra(_cd())
    made, skipped = same.replay(recipes)
    assert [c.name for c in made] == ['b1', 'v1', 'f1', 'f2'] and not skipped
    assert same.column('v1').title == 'Maximum over 220–225'
    assert same.column('f1').title == 'scaled' and np.isnan(same.column('b1').values[2])
    # other spectra: the band numbers belong to cd_10C / cd_20C only
    other = ValueTable.from_spectra(_cd(('cd_40C', 'cd_50C')))
    made, skipped = other.replay(recipes)
    assert [c.name for c in made] == ['v1', 'f1']
    assert skipped and 'b1' in skipped[0][1]                          # f2 = b1 * 2 is not made


def test_a_renamed_column_is_renamed_in_the_formulas():
    t = ValueTable.from_spectra(_cd())
    t.add_bands('Height (y)', [('222', [1, 2, 3])])                 # b1: cd_10C ... cd_30C
    t.add_bands('Area', [('300', [7, 8, 9])])                       # b2
    t.columns[-2].values[:] = np.nan                                 # b1: no value anywhere
    t.add_formula('b2 + 1')
    recipes = t.recipes()
    again = ValueTable.from_spectra(_cd())
    made, skipped = again.replay(recipes)
    assert [c.name for c in made] == ['b1', 'f1']                    # the old b2 is now b1
    assert again.column('f1').formula == 'b1 + 1' and list(again.column('f1').values) == [8, 9, 10]


class _Memory:
    """Stands for DataTableController: remembered + add_spectra."""
    remembered = None

    def add_spectra(self, table, spectra):
        return True, 'ok'


def _dialog(spectra, owner):
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    return DataTableDialog(None, spectra, commit_callback=owner.add_spectra)


def test_the_data_table_remembers_its_columns():
    owner = _Memory()
    dlg = _dialog(_cd(), owner)
    dlg.formula_edit.setText('sp1 - sp2')
    dlg.add_column()
    dlg.values.add_value({'kind': 'max', 'range_a': (215, 225)})
    dlg.values.formula_edit.setText('v1 * 2')
    dlg.values.add_formula()
    dlg.reject()                                                     # Close
    again = _dialog(_cd(), owner)
    assert [c.formula for c in again.table.formula_columns()] == ['sp1 - sp2']
    assert [c.name for c in again.values.table.columns][-2:] == ['v1', 'f1']
    assert 'From the last time' in again.values.message.text()
    assert 'From the last time' in again.message.text()
    # other spectra: sp1 would be another spectrum - only Values per spectrum
    other = _dialog(_cd(('a_1', 'a_2')), owner)
    assert other.table.formula_columns() == []
    assert [c.name for c in other.values.table.columns][-2:] == ['v1', 'f1']
    # a removed column is forgotten
    other.values.table.remove_column('f1')
    other.reject()
    last = _dialog(_cd(), owner)
    assert [c.name for c in last.values.table.columns][-1] == 'v1'


def test_formulas_added_as_spectra_are_not_made_again():
    owner = _Memory()
    dlg = _dialog(_cd(), owner)
    dlg.formula_edit.setText('sp1 - sp2')
    dlg.add_column()
    dlg.values.add_value({'kind': 'max', 'range_a': (215, 225)})
    assert dlg.add_as_spectra()                                      # closes the window
    again = _dialog(_cd(), owner)
    assert again.table.formula_columns() == []                      # added once is enough
    assert again.values.table.column('v1') is not None


def test_without_a_controller_nothing_is_remembered():
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    dlg = DataTableDialog(None, _cd())
    dlg.values.add_value({'kind': 'max', 'range_a': (215, 225)})
    dlg.reject()
    assert DataTableDialog(None, _cd()).values.table.column('v1') is None


def test_short_line_and_quick_help_on_each_tab():
    from src.views.dialogs.data_analysis.data_table_dialog import DataTableDialog
    dlg = DataTableDialog(None, _cd())
    texts = [w.text() for w in dlg.findChildren(QLabel)]
    assert not [t for t in texts if 'Two tabs' in t]                 # nothing above the tabs
    assert len(dlg.points_guide.text()) < 200 and len(dlg.values.guide.text()) < 200
    box = dlg.show_quick_help('points', run=False)
    assert 'Points' in box.windowTitle() and 'Ctrl+C' in box.text()
    box = dlg.values.show_quick_help('values', run=False)
    assert 'Values per spectrum' in box.windowTitle() and 'Add value' in box.text()
    assert dlg.quick_help_button.toolTip() and dlg.values.quick_help_button.toolTip()


def test_the_help_names_both_tabs():
    from src.help.user_guide_help import get_user_guide_help_content
    html = get_user_guide_help_content()
    assert 'id="data-table-points"' in html and 'Tab Values per spectrum' in html
    assert '(second tab)' not in html and 'narrowed' in html
