# src/views/tooltips.py
"""Long tooltips in several lines: a plain-text tooltip is shown by Qt as one
line however long it is (e.g. the explanation of Prominence in the Peak list
ran across the whole screen). When a tooltip is about to be shown, a plain
text longer than WIDTH characters per line is wrapped at WIDTH. install(app)
is called once at start-up (main.py).

Every window shows its tooltips with the names of its options in bold (a
window can switch this off: setProperty(RICH, False)): every tooltip in it -
of a widget, of a table cell or of a column heading - is shown as rich text
(rich()): in each line a short term before a colon is bold ("Automatic
(default): ..." -> "<b>Automatic (default)</b>: ..."), or what is marked
**so** when the text has such marks. The tooltip of a tick box or a round
choice button that does not begin with its name gets it first ("Show
legend: ..."), so that the option's name is bold too (named())."""

import html
import re
import textwrap

from PyQt5.QtCore import QEvent, QObject, QRect, Qt
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTabBar, QToolTip, QWidget

WIDTH = 80
RICH = 'rich_tooltips'            # a window property: False - its tooltips without bold terms
_TERM = re.compile(r'^(\s*)(\S[^:]{0,38}\S|\S)(:\s+\S.*)$')


def wrapped(text, width=WIDTH):
    """The text with lines of at most `width` characters (rich text and
    short texts unchanged)."""
    if not text or text.lstrip().startswith('<') or all(len(l) <= width for l in text.split('\n')):
        return text
    return '\n'.join(textwrap.fill(line, width) if len(line) > width else line
                     for line in text.split('\n'))


def rich(text, width=WIDTH):
    """The plain text as rich text for a tooltip: lines of at most `width`
    characters (as wrapped()), and in each of its lines the term before a
    colon bold - "Off (default): the data as measured" ->
    "<b>Off (default)</b>: the data as measured" (a term of at most 40
    characters, no space before the colon, text after it). When the text has
    **marks**, exactly the marked parts are bold instead. Rich text is kept."""
    if not text or Qt.mightBeRichText(text):
        return text
    marked = '**' in text
    out = []
    before = ''
    for line in text.split('\n'):
        # a line that goes on with the sentence of the line before (that one
        # ends with a word, a comma or a dash; this one begins with a small
        # letter) does not begin with a term
        going_on = bool(re.search(r'[\w,\-\u2013\u2014]\s*$', before)
                        and re.match(r'\s*[a-z]', line))
        before = line
        pieces = textwrap.wrap(line, width, drop_whitespace=False) if len(line) > width else [line]
        for k, piece in enumerate(pieces or ['']):
            e = html.escape(piece, quote=False)
            if marked:
                e = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', e)
            elif k == 0 and not going_on:
                m = _TERM.match(e)
                # not a sentence ("Click here. Then: ..."); an abbreviation
                # with a dot is a term ("Scatter corr. (SNV): ...")
                if m and not re.search(r'\. [A-Z]', m.group(2)):
                    e = f"{m.group(1)}<b>{m.group(2)}</b>{m.group(3)}"
            lead = len(e) - len(e.lstrip(' '))
            out.append('&nbsp;' * lead + e.lstrip(' '))
    return '<p style="white-space:pre">' + '<br>'.join(out) + '</p>'


def _label(button):
    """The name of a tick box / round button as a term: without "&", a
    trailing colon or "...", and without a formula after two spaces
    ("Peak intensity    I / Imax" -> "Peak intensity")."""
    text = re.split(r'\s{2,}', (button.text() or '').replace('&&', '\0').replace('&', '')
                    .replace('\0', '&').strip())[0]
    text = text.rstrip(':').rstrip('\u2026').rstrip('.').strip()
    return text if 0 < len(text) <= 40 and re.search(r'[A-Za-z]', text) and ':' not in text else ''


def named(button, text):
    """The tooltip of a tick box or round button with its name first, when it
    does not begin with it already (or with an own "Term: ..." line):
    "Show the legend" on "Legend" -> "Legend: show the legend"."""
    from PyQt5.QtWidgets import QAbstractButton
    if (not text or not isinstance(button, QAbstractButton) or not button.isCheckable()
            or Qt.mightBeRichText(text) or '**' in text):
        return text
    name = _label(button)
    first = text.split('\n', 1)[0]
    if not name or first.lower().startswith(name.lower()) or _TERM.match(first):
        return text
    return f"{name}: {text}"                         # its own capitals kept


def _tip_of(obj, pos):
    """(the tooltip text at pos, the rectangle it belongs to) - of a table
    cell or a column heading when obj is the viewport of a view, of a tab
    of a tab bar, else of the widget itself."""
    if isinstance(obj, QTabBar):
        index = obj.tabAt(pos)
        if index < 0:
            return obj.toolTip(), None
        return obj.tabToolTip(index) or obj.toolTip(), obj.tabRect(index)
    view = obj.parentWidget()
    if isinstance(view, QAbstractItemView) and view.viewport() is obj:
        if isinstance(view, QHeaderView):
            section = view.logicalIndexAt(pos)
            if section < 0:
                return None, None
            text = view.model().headerData(section, view.orientation(), Qt.ToolTipRole)
            start, size = view.sectionViewportPosition(section), view.sectionSize(section)
            rect = (QRect(start, 0, size, obj.height()) if view.orientation() == Qt.Horizontal
                    else QRect(0, start, obj.width(), size))
            return text, rect
        index = view.indexAt(pos)
        if not index.isValid():
            return view.toolTip(), None
        return index.data(Qt.ToolTipRole), view.visualRect(index)
    return obj.toolTip(), None


class _TooltipFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and isinstance(obj, QWidget):
            try:
                window = obj.window()
                if window is not None and window.property(RICH) is not False:
                    text, rect = _tip_of(obj, event.pos())
                    if not text:
                        return False                # nothing here: as Qt does it
                    text = named(obj, str(text))
                    if rect is None:
                        QToolTip.showText(event.globalPos(), rich(str(text)), obj)
                    else:
                        QToolTip.showText(event.globalPos(), rich(str(text)), obj, rect)
                    return True
            except Exception:                   # a tooltip is never worth an error
                return False
            try:
                tip = obj.toolTip()
                new = wrapped(tip)
                if new != tip:
                    obj.setToolTip(new)
            except Exception:                   # a tooltip is never worth an error
                pass
        return False


_filter = None


def install(app):
    global _filter
    if _filter is None:
        _filter = _TooltipFilter(app)
        app.installEventFilter(_filter)
        app.aboutToQuit.connect(uninstall)
        import atexit
        atexit.register(uninstall)
    return _filter


def uninstall():
    global _filter
    if _filter is None:
        return
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(_filter)
    except RuntimeError:
        pass
    _filter = None
