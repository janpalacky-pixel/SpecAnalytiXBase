"""Help -> What's New: one text file per version (resources/whats_new/<version>.md),
shown as a help page (newest first, with working links) and printable as the
GitHub release notes; a note in the status bar at the first start of a version."""
import os
import re
import sys
from html.parser import HTMLParser

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from src.help import whats_new_help as wn

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.ids, self.links = [], [], set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag not in ('meta', 'hr', 'br'):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append(tag)


def _parse(html):
    p = _Tags()
    p.feed(html)
    return p


def test_markdown_that_the_files_use():
    html = wn.markdown_to_html(
        "## What's new in 9.9\n\n### 9.9 in brief\n- **Bold** and *italic*, `<code>` "
        "[Help](help://user_guide#cursor) · [Details](#fixed)\n  continued line\n"
        "  - nested *item*\n- **Data range with *Apply linearization*** stays bold\n\n"
        "### Fixed\nA paragraph\non two lines.\n")
    assert '<h2 id="whats-new-in-99">' in html and '<h3 id="99-in-brief">' in html
    assert '<b>Bold</b> and <i>italic</i>, <code>&lt;code&gt;</code>' in html
    assert '<a href="help://user_guide#cursor">Help</a>' in html and '<a href="#fixed">' in html
    assert 'continued line<ul><li>nested <i>item</i></li></ul></li>' in html.replace('\n', '')
    assert '<b>Data range with <i>Apply linearization</i></b> stays bold' in html
    assert '<h3 id="fixed">Fixed</h3>\n<p>A paragraph on two lines.</p>' in html
    assert _parse(html).errors == []


def test_versions_are_listed_newest_first(tmp_path):
    for v in ('1.4.2', '1.10.0', '1.5.0'):
        (tmp_path / f'{v}.md').write_text(f'## What\'s new in {v}\n')
    assert [os.path.basename(p) for p in wn.version_files(str(tmp_path))] == \
        ['1.10.0.md', '1.5.0.md', '1.4.2.md']


def test_the_current_version_has_its_notes():
    from src.version import __version__
    assert os.path.isfile(os.path.join(ROOT, 'resources', 'whats_new', f'{__version__}.md')), \
        "Write resources/whats_new/<version>.md for the new version (Help > What's New)"


def test_page_is_well_formed_and_every_link_works():
    from src.help import help_window
    html = wn.get_whats_new_help_content()
    page = _parse(html)
    assert page.errors == [] and page.stack == []
    for heading in ("What's new in 1.5.0", '1.5.0 in brief', 'New', 'Faster', 'Easier to use',
                    'Changed results', 'Fixed', 'Safer', 'Upgrading'):
        assert f'>{heading}</h' in html
    assert page.links
    for link in page.links:
        if link.startswith('#'):
            assert link[1:] in page.ids, link
            continue
        m = re.match(r'help://([a-z_0-9]+)(?:#(.+))?$', link)
        assert m, link
        key, anchor = m.groups()
        assert key in help_window._REGISTRY, link
        if anchor:
            module, _, content_fn = help_window._REGISTRY[key]
            mod = __import__(module, fromlist=[content_fn])
            assert f'id="{anchor}"' in getattr(mod, content_fn)(), link


def test_github_release_notes_have_no_help_links():
    path = os.path.join(ROOT, 'resources', 'whats_new', '1.5.0.md')
    text = wn.github_markdown(path)
    assert text.startswith("## What's new in 1.5.0") and 'help://' not in text
    assert '- **Group Statistics**' in text and ' · ' not in text.split('### New')[0]


def test_help_menu_entry(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.controllers.core.main_controller import MainController
    from src.help import help_window
    opened = []
    monkeypatch.setattr(help_window, 'open_help_topic', lambda parent, key, anchor=None: opened.append(key))
    mc = MainController()
    try:
        actions = [a.text() for a in mc.view.menuHelp.actions()]
        assert actions.index("What's New") == actions.index('Quick Start') + 1
        mc.view.actionWhatsNew.trigger()                 # the small window of this version
        from src.version import __version__
        dlg = mc._whats_new_window
        assert dlg.isVisible() and dlg.version == __version__ and opened == []
        dlg.all_button.click()                           # ... and from there the full page
        assert opened == ['whats_new']
        dlg.close()
        monkeypatch.setattr(wn, 'brief_markdown', lambda v: '')    # no notes: the page directly
        mc.view.actionWhatsNew.trigger()
        assert opened == ['whats_new', 'whats_new']
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_dont_show_again_can_be_switched_off_in_help_whats_new(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.controllers.core.main_controller import MainController
    from src.version import __version__
    mc = MainController()
    prefs = mc.autosave_controller.preferences
    try:
        prefs.set('whats_new_hidden_for', __version__)    # switched off at some start
        assert mc.announce_new_version(__version__, delay_ms=0) is False
        mc.view.actionWhatsNew.trigger()
        dlg = mc._whats_new_window
        assert dlg.dont_show.isChecked()                  # shows that it is off
        dlg.dont_show.setChecked(False)                   # switched on again
        dlg.close_button.click()
        assert prefs.get('whats_new_hidden_for') == ''
        assert mc.announce_new_version(__version__, delay_ms=0) is True
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_brief_list_of_a_version():
    md = wn.brief_markdown('1.5.0')
    assert md.startswith('- **Group Statistics**') and '### New' not in md
    assert wn.brief_markdown('0.0.1') == ''


def test_window_at_start_until_dont_show_again(tmp_path, monkeypatch):
    """A new version shows a small window with its "in brief" list at every
    start, until "Don't show this again" is ticked; the next version shows
    its own list again."""
    import time
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from PyQt5.QtCore import QUrl
    from src.controllers.core.main_controller import MainController
    from src.help import help_window
    opened = []
    monkeypatch.setattr(help_window, 'open_help_topic',
                        lambda parent, key, anchor=None: opened.append((key, anchor)))
    real = wn.brief_markdown
    monkeypatch.setattr(wn, 'brief_markdown', lambda v: (
        real(v) if v == '1.5.0' else '- **Something new**\n'))
    mc = MainController()

    def started(version):
        mc._whats_new_window = None
        shown = mc.announce_new_version(version, delay_ms=0)
        end = time.time() + 3
        while shown and mc._whats_new_window is None and time.time() < end:
            app.processEvents()
        return mc._whats_new_window if shown else None
    try:
        dlg = started('1.5.0')
        assert dlg is not None and dlg.isVisible()
        assert dlg.windowTitle() == "What's new in SpecAnalytiXBase 1.5.0"
        assert 'Group Statistics' in dlg.text.toPlainText() and 'Peak-fit maps' not in \
            dlg.text.toPlainText().split('2D Map')[0]
        dlg._open_link(QUrl('help://group_statistics_tutorial'))
        dlg._open_link(QUrl('help://map2d#unmixing'))
        dlg._open_link(QUrl('#faster'))
        dlg.all_button.click()
        assert opened == [('group_statistics_tutorial', None), ('map2d', 'unmixing'),
                          ('whats_new', 'faster'), ('whats_new', None)]
        dlg.close_button.click()                               # closed without ticking
        dlg = started('1.5.0')
        assert dlg is not None                                 # ... so it comes again
        dlg.dont_show.setChecked(True)
        dlg.close_button.click()
        assert mc.autosave_controller.preferences.get('whats_new_hidden_for') == '1.5.0'
        assert started('1.5.0') is None                        # not for this version any more
        assert started('1.6.0') is not None                    # the next version shows its list
    finally:
        if mc._whats_new_window is not None:
            mc._whats_new_window.close()
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()


def test_no_window_without_notes_for_the_version(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.controllers.core.main_controller import MainController
    mc = MainController()
    try:
        assert mc.announce_new_version('0.0.1', delay_ms=0) is False
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
