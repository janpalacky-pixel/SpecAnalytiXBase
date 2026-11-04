# src/views/tooltips.py
"""Long tooltips in several lines: a plain-text tooltip is shown by Qt as one
line however long it is (e.g. the explanation of Prominence in the Peak list
ran across the whole screen). When a tooltip is about to be shown, a plain
text longer than WIDTH characters per line is wrapped at WIDTH. install(app)
is called once at start-up (main.py).

A window can ask for tooltips with the names of its options in bold
(setProperty(RICH, True), e.g. Peak Fitting): every tooltip in it - of a
widget, of a table cell or of a column heading - is then shown as rich text
(rich()): in each line a short term before a colon is bold ("Automatic
(default): ..." -> "<b>Automatic (default)</b>: ..."), or what is marked
**so** when the text has such marks."""

import html
import re
import textwrap

from PyQt5.QtCore import QEvent, QObject, QRect, Qt
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTabBar, QToolTip, QWidget

WIDTH = 80
RICH = 'rich_tooltips'            # a window property: its tooltips with bold terms
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
    for line in text.split('\n'):
        pieces = textwrap.wrap(line, width, drop_whitespace=False) if len(line) > width else [line]
        for k, piece in enumerate(pieces or ['']):
            e = html.escape(piece, quote=False)
            if marked:
                e = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', e)
            elif k == 0:
                m = _TERM.match(e)
                if m and '. ' not in m.group(2):
                    e = f"{m.group(1)}<b>{m.group(2)}</b>{m.group(3)}"
            lead = len(e) - len(e.lstrip(' '))
            out.append('&nbsp;' * lead + e.lstrip(' '))
    return '<p style="white-space:pre">' + '<br>'.join(out) + '</p>'


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
                if window is not None and window.property(RICH):
                    text, rect = _tip_of(obj, event.pos())
                    if not text:
                        return False                # nothing here: as Qt does it
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
