# src/views/button_icons.py
"""Icons on the buttons of every window and dialog (not the main window, whose
buttons have their own): chosen by the button's text - Close, Save..., Copy,
Export..., Add as New, Run, Reset to defaults, ... - so every dialog gets
them without changing its code. install(app) is called once at start-up
(main.py); a button gets its icon when it is first shown.

A button keeps its own icon; it gets none when its text starts with a symbol
(e.g. "▶  Run NMF", which has one already), when it is the orange "?", when it
is too narrow for an icon, or when its property "noAutoIcon" is True. When the
icon would cut off the text (a narrow panel), it is taken away again."""

import re

from PyQt5.QtCore import QEvent, QObject, QSize, QTimer
from PyQt5.QtWidgets import QMainWindow, QPushButton

from src.views import icons

_WIDGETSIZE_MAX = 16777215
_ICON = QSize(16, 16)

# (regular expression on the cleaned-up, lower-case text, icon). The first
# that matches wins. 'std:NAME' is a standard icon of the style.
RULES = [
    (r'^(close|close window)$', 'std:SP_DialogCloseButton'),
    (r'^(cancel|cancel edit|abort)$', 'std:SP_DialogCancelButton'),
    (r'^(ok|done)$', 'std:SP_DialogOkButton'),
    (r'^yes( to all)?$', 'std:SP_DialogYesButton'),
    (r'^no( to all)?$', 'std:SP_DialogNoButton'),
    (r'^(help|full help)$', 'help'),
    (r'^(apply\b.*|use these points)$', 'std:SP_DialogApplyButton'),
    (r'^(add as new|add\b.*|send to main list|store as [ab])$', 'add'),
    (r'^copy plot', 'plot'),
    (r'^copy\b', 'copy'),
    (r'^(save\b.*|export\b.*)$', 'std:SP_DialogSaveButton'),
    (r'^(open|load\b.*|import\b.*|browse|from file|from table file|open file)$',
     'std:SP_DialogOpenButton'),
    (r'^open folder$', 'std:SP_DirOpenIcon'),
    (r'^(delete\b.*|remove\b.*)$', 'std:SP_TrashIcon'),
    (r'^clear\b.*$', 'std:SP_LineEditClearButton'),
    (r'^(reset\b.*|restore defaults|revert\b.*|restore generated draft)$',
     'std:SP_DialogResetButton'),
    (r'^(refresh\b.*|update\b.*|recompute\b.*|re-detect\b.*)$', 'std:SP_BrowserReload'),
    (r'^stop$', 'stop'),
    (r'^(run\b.*|start|compute\b.*|calculate|fit|fit peaks|detect cosmic rays|'
     r'auto-detect\b.*|run preview)$', 'run'),
    (r'^(plot|plot all|draw plot|show overlay plot|preview reconstruction)$', 'plot'),
    (r'^(show as table|peak list|copy table|show all metrics \(table\))$', 'table'),
    (r'^(previous|back)$', 'std:SP_ArrowBack'),
    (r'^next$', 'std:SP_ArrowForward'),
    (r'^download\b.*$', 'std:SP_ArrowDown'),
]
_COMPILED = [(re.compile(p), icon) for p, icon in RULES]
_DRAWN = {'run': icons.run_icon, 'add': icons.add_icon, 'copy': icons.copy_icon,
          'stop': icons.stop_icon, 'plot': icons.plot_icon, 'table': icons.table_icon,
          'help': icons.help_icon}


def clean(text):
    """'&Save…' -> 'save'; 'Copy to Clipboard' -> 'copy to clipboard'."""
    text = (text or '').replace('&&', '\0').replace('&', '').replace('\0', '&')
    text = text.replace('…', '').replace('...', '').strip().rstrip(':').strip()
    return re.sub(r'\s+', ' ', text).lower()


def icon_name(text):
    """The icon for a button text, or None."""
    raw = (text or '').strip()
    if not raw or not (raw[0].isalnum() or raw[0] == '&'):   # "?", "▶  Run", "💾 Export", ...
        return None
    t = clean(raw)
    for pattern, name in _COMPILED:
        if pattern.match(t):
            return name
    return None


def make_icon(name, widget=None):
    if name.startswith('std:'):
        return icons.standard(name[4:], widget)
    return _DRAWN[name]()


def _fits(button):
    """Room for an icon next to the text (some buttons have a fixed width)."""
    limit = button.maximumWidth()
    if limit >= _WIDGETSIZE_MAX:
        return True
    need = button.fontMetrics().horizontalAdvance(button.text()) + _ICON.width() + 30
    return need <= limit


def decorate(button):
    """Give the button its icon (when it has none of its own). Returns the
    icon name or None."""
    if button.property('noAutoIcon'):
        return None
    auto = button.property('_autoIconText')
    if not button.icon().isNull() and auto is None:
        return None                                 # an icon of its own
    if auto is not None and auto == button.text():
        return button.property('_autoIconName')     # done already
    if button.property('_autoIconTooNarrow') == button.text():
        return None                                 # tried: the text did not fit
    window = button.window()
    if isinstance(window, QMainWindow):
        return None                                 # the main window has its own icons
    name = icon_name(button.text())
    if name is None or not _fits(button):
        if auto is not None:                        # the text changed: no icon any more
            from PyQt5.QtGui import QIcon
            button.setIcon(QIcon())
            button.setProperty('_autoIconText', None)
        if name is not None:                        # too narrow: nor on its row
            button.setProperty('_autoIconTooNarrow', button.text())
            _later(button, _drop_row)
        return None
    button.setIcon(make_icon(name, button))
    button.setIconSize(_ICON)
    button.setProperty('_autoIconText', button.text())
    button.setProperty('_autoIconName', name)
    _later(button, _drop_if_clipped)
    return name


def _later(button, function):
    """function(button) once the window is laid out (a timer that is a child
    of the button, so it never outlives it)."""
    timer = QTimer(button)
    timer.setSingleShot(True)
    timer.timeout.connect(lambda b=button, t=timer: (function(b), t.deleteLater()))
    timer.start(0)


def _drop_if_clipped(button):
    """Take the icon away again when the button is now too narrow for its
    text (it sits in a narrow panel)."""
    try:
        if button.property('_autoIconText') is None or not button.isVisible():
            return
        window = button.window()
        if window.layout() is not None:
            window.layout().activate()              # the sizes with the icon
        if button.width() + 2 >= button.sizeHint().width():
            return
        _drop_row(button)
    except RuntimeError:                            # the button is gone already
        pass


def _drop_row(button):
    """No icon on this button, nor on the others in its row (a row with icons
    on some buttons only looks odd)."""
    try:
        row = [button]
        parent = button.parentWidget()
        if parent is not None:
            y = button.geometry().center().y()
            row += [b for b in parent.findChildren(QPushButton)
                    if b is not button and b.parentWidget() is parent and b.isVisible()
                    and b.property('_autoIconText') is not None
                    and abs(b.geometry().center().y() - y) < max(4, button.height() // 2)]
        from PyQt5.QtGui import QIcon
        for b in row:
            b.setIcon(QIcon())
            b.setProperty('_autoIconTooNarrow', b.text())
            b.setProperty('_autoIconText', None)
            b.setProperty('_autoIconName', None)
    except RuntimeError:                            # the button is gone already
        pass


class _ButtonIconFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QPushButton):
            try:
                decorate(obj)
            except Exception:                       # an icon is never worth an error
                pass
        return False


_filter = None


def install(app):
    """Icons on dialog buttons from now on (once per application)."""
    global _filter
    if _filter is None:
        _filter = _ButtonIconFilter(app)
        app.installEventFilter(_filter)
        # A Python event filter must not run while Python is shutting down
        # (the windows are destroyed then): remove it first.
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
