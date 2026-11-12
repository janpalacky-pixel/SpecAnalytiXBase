# src/views/toolbar_mode.py
"""Zoom or Pan chosen in a plot toolbar (matplotlib's, under every plot) is
easy to see: the button pressed in has an orange frame on a light orange
background (matplotlib's own look of a pressed button is hardly different
from a normal one), and an orange note next to the buttons says what is on
and how to end it, e.g. "Pan on - click Pan again to end".

While Zoom or Pan is on, a click on the plot zooms or pans - so a click on
a line or on a name in the legend does nothing then (plot_mouse_controller
also says so in the status bar). Before, users did not see why.

Installed once for the application (main.py, MainController): an event
filter decorates every plot toolbar when it is first shown (QEvent.Polish)
and gives its plot the wheel zoom and dragging (plot_navigation.py),
the main plot's and those of the tool windows alike - no window has to do
anything. The look only changes while a button is pressed in, so pictures
of the windows are the same as before."""

from PyQt5.QtCore import QEvent, QObject, QTimer
from PyQt5.QtWidgets import QLabel

ORANGE = '#E65100'
CHECKED_STYLE = ("QToolButton:checked { background-color: #FFE0B2; "
                 f"border: 2px solid {ORANGE}; border-radius: 3px; }}")
NOTES = {'pan': "Pan on – drag moves the plot; click Pan again to end",
         'zoom': "Zoom on – drag a rectangle; click Zoom again to end"}

_filter = None


def _is_plot_toolbar(widget):
    try:
        from matplotlib.backends.backend_qt import NavigationToolbar2QT
    except Exception:
        return False
    return isinstance(widget, NavigationToolbar2QT)


def mode_of(toolbar):
    """'pan', 'zoom' or '' - what the toolbar's buttons are set to."""
    name = str(getattr(getattr(toolbar, 'mode', ''), 'name', '') or '').lower()
    return name if name in NOTES else ''


def decorate(toolbar):
    """The pressed-in look and the note (once per toolbar). Returns the note."""
    if getattr(toolbar, '_sax_mode_note', None) is not None:
        return toolbar._sax_mode_note
    toolbar.setStyleSheet((toolbar.styleSheet() or '') + '\n' + CHECKED_STYLE)
    note = QLabel('', toolbar)
    note.setObjectName('sax_mode_note')
    note.setStyleSheet(f"QLabel {{ color: {ORANGE}; font-weight: bold; padding: 0 6px; }}")
    note.setToolTip("While <b>Zoom</b> or <b>Pan</b> is on, a click on the plot zooms or pans: "
                    "a click on a line or on a name in the legend does nothing.")
    before = None
    loc = getattr(toolbar, 'locLabel', None)
    for action in toolbar.actions():
        if loc is not None and toolbar.widgetForAction(action) is loc:
            before = action
            break
    action = (toolbar.insertWidget(before, note) if before is not None
              else toolbar.addWidget(note))
    toolbar._sax_mode_note = note
    toolbar._sax_mode_action = action

    def update(*_):
        try:
            mode = mode_of(toolbar)
            note.setText(NOTES.get(mode, ''))
            action.setVisible(bool(mode))
        except RuntimeError:                   # the toolbar is gone
            pass
    def update_later(*_):
        # A click on the button first ticks it (toggled) and only then runs
        # matplotlib's pan() / zoom(), which sets the mode: read right away,
        # the mode was the one before (the note named the other tool).
        # So: after the click is handled.
        QTimer.singleShot(0, update)
    for name in ('pan', 'zoom'):
        a = getattr(toolbar, '_actions', {}).get(name)
        if a is not None:
            a.toggled.connect(update_later)
            a.triggered.connect(update_later)
    update()
    return note


class _Filter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Polish and _is_plot_toolbar(obj):
            try:
                decorate(obj)
            except Exception:
                pass
            try:                               # the wheel zoom and dragging (plot_navigation.py)
                from src.views import plot_navigation
                plot_navigation.attach(getattr(obj, 'canvas', None))
            except Exception:
                pass
        return False


def install(app):
    """Once for the application; again: nothing. Removed again before the
    application ends (as tooltips.install): a filter still installed while
    Python tears the objects down can crash the interpreter at exit."""
    global _filter
    if _filter is None and app is not None:
        _filter = _Filter(app)
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
