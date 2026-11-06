"""Help › Search the help… (F1): a word in all help pages at once; a hit
names its page and section and opens the page there."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def test_sections_of_a_page():
    from src.help.help_search import sections, search
    page = ('<html><body><p>Intro text.</p><h2 id="a">Legend</h2><p>The legend window '
            'shows names.</p><h3 id="b">Colours</h3><p>Line colours &amp; legend.</p>'
            '<p id="c">Save at 600 dpi.</p></body></html>')
    secs = sections(page)
    assert [s[0] for s in secs] == [None, 'a', 'b', 'c']
    assert secs[1][1] == 'Legend' and 'Line colours & legend' in secs[2][2]
    entries = [('ug', 'User Guide', a, h, t) for a, h, t in secs]
    hits = search('legend', entries)
    assert hits[0]['anchor'] == 'a'                       # in its heading: first
    assert {h['anchor'] for h in hits} == {'a', 'b'}
    assert [h['anchor'] for h in search('600 DPI', entries)] == ['c']   # every word, any case
    assert search('nothing here', entries) == [] and search('  ', entries) == []


def test_all_help_pages_and_the_window():
    from src.help import help_search
    hits = help_search.search('isosbestic')
    assert hits and hits[0]['key'] in ('isosbestic_point', 'user_guide')
    assert any(h['anchor'] == 'publication' for h in help_search.search('600 dpi'))
    assert not any(h['key'] == 'developer_guide' for h in help_search.search('pytest'))
    from src.views.dialogs.misc.help_search_dialog import HelpSearchDialog
    opened = []
    dlg = HelpSearchDialog(open_topic=lambda k, a: opened.append((k, a)))
    dlg.field.setText('start page')
    found = dlg.find()
    assert found and dlg.results.count() == len(found)
    assert 'found' in dlg.count_label.text()
    dlg._enter()                                          # Enter: the first one
    assert opened and opened[0] == (found[0]['key'], found[0]['anchor'])
    assert dlg.find('xyzzyq') == [] and dlg.count_label.text() == 'Nothing found.'
