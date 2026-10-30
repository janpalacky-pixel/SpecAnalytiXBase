# src/views/plot_only_mode.py
"""A tool window open beside the main plot: while it is open, only the plot of
the main window and its Basic plot options can be used - zoom, pan, home and
save in the plot's toolbar, the x/y read-out, the cursor, the plot type,
scales, colours, legend - so you can look closely at what the window shows
(e.g. the peaks marked by the Peaks window) or compare it with the plot.
Everything else in the main window that could change the window's data is
greyed out until it closes: the spectra list and its buttons, the menus and
the buttons under the menu bar, the keyboard shortcuts, the right-click menu
on the plot, dropping files on the window, and closing the main window. A
slim orange line above the plot says so, with "Hide the window" (to see the
whole main window; "Show the window" brings it back) and "Close the window".

run_beside_plot(dialog, name=None) replaces dialog.exec_(): it shows the
window (not modal), waits until it closes - the code after it runs as
before - and returns its result. A window that has on_main_plot_redrawn() is
told when the plot was drawn again meanwhile (e.g. another plot type), to
draw its marks again. add_apply_button(dialog, apply) adds an Apply button
next to OK, for windows whose settings change the plot only at OK."""

import inspect
import sys
import types

from PyQt5.QtCore import QEvent, QEventLoop, QObject, Qt
from PyQt5.QtWidgets import (QAction, QBoxLayout, QDialog, QDialogButtonBox, QFrame,
                             QHBoxLayout, QLabel, QMainWindow, QPushButton, QShortcut,
                             QSizePolicy, QStatusBar, QWidget)

BANNER_NAME = 'plot_only_banner'          # kept when the plot is drawn again
BANNER_STYLE = ("QFrame#plot_only_banner { background: #FFF3E0; border: 1px solid #F57C00; "
                "border-radius: 3px; } QFrame#plot_only_banner QLabel { color: #8A4B00; }")


def main_window_of(widget):
    """The main window a dialog belongs to (None if it has none)."""
    w = widget
    while w is not None:
        if isinstance(w, QMainWindow):
            return w
        w = w.parentWidget()
    return None


def _plot_area(main):
    """The plot with its toolbar (None: this main window has no plot)."""
    return getattr(main, 'graphicsView', None)


def _usable(main):
    """The parts of the main window that stay usable: the plot and its Basic
    plot options (they only change how the plot looks)."""
    return [w for w in (_plot_area(main), getattr(main, 'groupBox_basic_plot_options', None))
            if w is not None]


class PlotOnlyLock(QObject):
    """Grey out everything of the main window except its plot (engage), and
    put it back as it was (release)."""

    def __init__(self, main, text, dialog=None):
        super().__init__(main)
        self.main, self.text, self.dialog = main, text, dialog
        self.plot = _plot_area(main)
        self.usable = _usable(main)
        self._widgets, self._actions, self._shortcuts = [], [], []
        self.banner = None

    def _inside_plot(self, obj):
        while obj is not None and not isinstance(obj, QWidget):
            obj = obj.parent()
        return obj is not None and any(obj is u or u.isAncestorOf(obj) for u in self.usable)

    def _of_main_window(self, obj):
        """Belongs to the main window itself (not to the open dialog or another
        window, and not to the plot)."""
        while obj is not None and not isinstance(obj, QWidget):
            obj = obj.parent()
        return obj is not None and obj.window() is self.main and not self._inside_plot(obj)

    def _grey_out(self, parent):
        for child in parent.children():
            if not isinstance(child, QWidget) or child.isWindow():
                continue                                   # the dialog, other windows
            if child in self.usable:
                continue
            if any(child.isAncestorOf(u) for u in self.usable):
                self._grey_out(child)                      # down to the plot, keep it
                continue
            if isinstance(child, QStatusBar):
                continue                                   # only text, it may change
            self._widgets.append((child, not child.testAttribute(Qt.WA_ForceDisabled)))
            child.setEnabled(False)

    def engage(self):
        self._grey_out(self.main)
        for action in self.main.findChildren(QAction):
            if self._of_main_window(action) and action.isEnabled():
                self._actions.append(action)
                action.setEnabled(False)
        for shortcut in self.main.findChildren(QShortcut):
            if self._of_main_window(shortcut) and shortcut.isEnabled():
                self._shortcuts.append(shortcut)
                shortcut.setEnabled(False)
        # the slim orange line at the top of the plot area (above the plot)
        self.banner = self._make_banner()
        layout = self.plot.layout()
        if isinstance(layout, QBoxLayout):
            layout.insertWidget(0, self.banner)
        else:                                       # no layout: over the top of the plot
            self.banner.setParent(self.plot)
            self.banner.setFixedWidth(max(self.plot.width() - 8, 200))
            self.banner.move(4, 4)
            self.banner.show()
            self.banner.raise_()
        self.main.installEventFilter(self)
        self.main.plot_only_lock = self
        return self

    def _make_banner(self):
        banner = QFrame()
        banner.setObjectName(BANNER_NAME)
        banner.setStyleSheet(BANNER_STYLE)
        banner.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        row = QHBoxLayout(banner)
        row.setContentsMargins(8, 2, 4, 2)
        label = QLabel(self.text)
        label.setWordWrap(True)
        row.addWidget(label, 1)
        self.toggle_button = QPushButton("Hide the window")
        self.toggle_button.setToolTip("Hide the window to see the whole main window; "
                                      "\"Show the window\" brings it back")
        self.toggle_button.clicked.connect(self.toggle_window)
        self.close_button = QPushButton("Close the window")
        self.close_button.clicked.connect(lambda: self.dialog is not None and self.dialog.reject())
        for b in (self.toggle_button, self.close_button):
            b.setAutoDefault(False)
            row.addWidget(b)
        if self.dialog is None:
            self.toggle_button.hide()
            self.close_button.hide()
        banner.label = label
        return banner

    def toggle_window(self):
        """Hide the tool window (to see the whole main window) or show it again."""
        if self.dialog is None:
            return
        if self.dialog.isVisible():
            self.dialog.hide()
            self.toggle_button.setText("Show the window")
        else:
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
            self.toggle_button.setText("Hide the window")

    def plot_redrawn(self):
        """The main plot was drawn again (e.g. another plot type): the banner
        back on top, and the window may draw its marks again."""
        layout = self.plot.layout()
        if self.banner is not None and isinstance(layout, QBoxLayout):
            if layout.indexOf(self.banner) != 0:
                layout.removeWidget(self.banner)
                layout.insertWidget(0, self.banner)
        hook = getattr(self.dialog, 'on_main_plot_redrawn', None)
        if callable(hook):
            try:
                hook()
            except Exception:
                pass

    def release(self):
        self.main.removeEventFilter(self)
        for widget, enabled in reversed(self._widgets):
            try:
                widget.setEnabled(enabled)
            except RuntimeError:                           # deleted meanwhile
                pass
        for action in self._actions:
            try:
                action.setEnabled(True)
            except RuntimeError:
                pass
        for shortcut in self._shortcuts:
            try:
                shortcut.setEnabled(True)
            except RuntimeError:
                pass
        if self.banner is not None:
            try:
                self.banner.setParent(None)
                self.banner.deleteLater()
            except RuntimeError:                           # gone with a new plot
                pass
            self.banner = None
        if getattr(self.main, 'plot_only_lock', None) is self:
            self.main.plot_only_lock = None
        self._widgets, self._actions, self._shortcuts = [], [], []

    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.main and kind == QEvent.Close:
            event.ignore()                     # close the tool window first
            if self.dialog is not None:
                self.dialog.raise_()
                self.dialog.activateWindow()
            return True
        if kind in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            event.ignore()
            return True
        return False


def plot_only(main):
    """The lock in force on this main window now, or None."""
    return getattr(main, 'plot_only_lock', None) if main is not None else None


def release_mouse_capture():
    """Let go of the mouse. The window is usually opened by a click (a menu,
    Run); on Windows the main window can keep the mouse captured after it,
    and then every click - also on the tool window's own buttons and its X -
    goes to the main window. A modal window used to end that capture; a
    window beside the plot does it here."""
    grabber = QWidget.mouseGrabber()
    if grabber is not None:
        grabber.releaseMouse()
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.ReleaseCapture()
        except Exception:
            pass


def _exec_replaced(dialog):
    """exec_ replaced by a test (it drives the window itself)."""
    return ('exec_' in getattr(dialog, '__dict__', {})
            or isinstance(inspect.getattr_static(type(dialog), 'exec_'), types.FunctionType))


def banner_text(dialog, name=None):
    """The text of the orange line above the plot."""
    what = f"The {name} window" if name else f"\u201c{dialog.windowTitle() or 'The window'}\u201d"
    return f"{what} is open: only the plot (zoom, pan, save) and the Basic plot options can be used."


def run_beside_plot(dialog, name=None):
    """Show `dialog` beside the main plot and wait until it closes; returns
    its result (as dialog.exec_()). name: how the line above the plot calls
    the window (its title when None). Without a main window with a plot (or
    when another window already holds it) the dialog is simply modal."""
    # a stand-in or a window driven by a test: as it wants
    if not isinstance(dialog, QDialog) or _exec_replaced(dialog):
        return dialog.exec_()
    main = main_window_of(dialog.parentWidget())
    if main is None or _plot_area(main) is None or plot_only(main):
        return dialog.exec_()
    lock = PlotOnlyLock(main, banner_text(dialog, name), dialog)
    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    lock.engage()
    try:
        dialog.setWindowModality(Qt.NonModal)
        release_mouse_capture()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        # once more when the click that opened it has been handled
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, release_mouse_capture)
        if dialog.isVisible():
            loop.exec_()
    finally:
        lock.release()
        lock.deleteLater()
    return dialog.result()


def add_apply_button(dialog, apply):
    """An Apply button just before OK: apply() puts the settings shown on the
    plot, and the window stays open (Cancel then does not take them back)."""
    button = QPushButton("Apply")
    button.setAutoDefault(False)
    button.setToolTip("Show these settings on the plot now; the window stays open")
    button.clicked.connect(lambda: apply())
    for box in dialog.findChildren(QDialogButtonBox):
        ok = box.button(QDialogButtonBox.Ok)
        if ok is not None:
            box.addButton(button, QDialogButtonBox.ApplyRole)
            dialog.apply_button = button
            return button
    for layout in dialog.findChildren(QHBoxLayout):
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if isinstance(w, QPushButton) and w.text().replace('&', '') == 'OK':
                layout.insertWidget(i, button)
                dialog.apply_button = button
                return button
    dialog.layout().addWidget(button)
    dialog.apply_button = button
    return button
