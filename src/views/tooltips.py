# src/views/tooltips.py
"""Long tooltips in several lines: a plain-text tooltip is shown by Qt as one
line however long it is (e.g. the explanation of Prominence in the Peak list
ran across the whole screen). When a tooltip is about to be shown, a plain
text longer than WIDTH characters per line is wrapped at WIDTH. install(app)
is called once at start-up (main.py)."""

import textwrap

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QWidget

WIDTH = 80


def wrapped(text, width=WIDTH):
    """The text with lines of at most `width` characters (rich text and
    short texts unchanged)."""
    if not text or text.lstrip().startswith('<') or all(len(l) <= width for l in text.split('\n')):
        return text
    return '\n'.join(textwrap.fill(line, width) if len(line) > width else line
                     for line in text.split('\n'))


class _TooltipFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and isinstance(obj, QWidget):
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
