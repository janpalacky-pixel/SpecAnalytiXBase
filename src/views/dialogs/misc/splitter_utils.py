"""Splitters that move smoothly and never swallow a whole panel.

Two problems seen in several windows (found 2026-10-18):

* The control panel had a FIXED width (setFixedWidth(400)). A splitter cannot
  make such a panel narrower or wider, so dragging the handle did nothing
  until the panel suddenly collapsed to 0 -- it "could not move gradually".
* With collapsible children (the Qt default) dragging a handle far enough
  hides a panel completely; it is then easy to lose and hard to get back.

scrollable_panel() puts a control panel into a scroll area (a narrower or
shorter panel gets a scroll bar instead of squeezing or hiding its
controls) and releases a fixed width; no_collapse() keeps every part of a
splitter at a minimum size. Together they behave like the splitters of
PCA Scores & Loadings, SVD Analysis or NMF.

Found next (2026-10-19): with the fixed width gone, a window opened with its
control panel narrower than the controls need -- a sideways scroll bar and
cut-off controls right after opening (Automated Baseline, X-axis alignment,
Resolution enhancement, Spike removal, SVD Interpolation, Group Statistics;
Group Statistics could before not be narrower than ~1 810 px and so always
opened that wide, even on a smaller screen). So when the window is first
shown, fit_panel() gives each such panel the width its controls need (at
least its former fixed width), taking it from the other parts of the
splitter, and makes the window wider only if that is not enough -- never
wider than the screen. Afterwards the user can drag it narrower again.
"""
from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QFrame, QScrollArea, QSplitter

_QWIDGETSIZE_MAX = (1 << 24) - 1


def scrollable_panel(panel, min_width=240):
    """Return `panel` inside a frameless QScrollArea that the splitter can
    resize gradually. A fixed or maximum width set on the panel is released
    (narrow: the contents stay usable through the scroll bars; wide: they
    use the room)."""
    preferred = 0
    if panel.minimumWidth() == panel.maximumWidth() and panel.minimumWidth() > 0:
        preferred = panel.minimumWidth()        # the width it used to have
        panel.setMinimumWidth(0)
    # a maximum width would leave the scroll area's extra room empty when
    # the splitter makes the panel wider (Interactive subtraction had 350)
    panel.setMaximumWidth(_QWIDGETSIZE_MAX)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setWidget(panel)
    area.setMinimumWidth(min_width)
    area.preferred_width = preferred
    fit_on_first_show(area)
    return area


class _FitOnFirstShow(QObject):
    def __init__(self, area):
        super().__init__(area)
        self.done = False

    def eventFilter(self, obj, event):
        if not self.done and event.type() == QEvent.Show:
            self.done = True
            # after the window has its size and the splitter its sizes
            QTimer.singleShot(0, lambda: fit_panel(obj))
        return False


def fit_on_first_show(area):
    """When `area` (a QScrollArea in a horizontal splitter) is first shown,
    fit_panel() it. scrollable_panel() does this by itself."""
    area._fit_filter = _FitOnFirstShow(area)
    area.installEventFilter(area._fit_filter)
    return area


def needed_width(area):
    """Width the scroll area needs to show its panel without a sideways
    scroll bar: the panel's minimum (or its former fixed width), plus a
    vertical scroll bar if the panel is taller than the area."""
    panel = area.widget()
    need = max(panel.minimumSizeHint().width(), getattr(area, 'preferred_width', 0) or 0)
    if panel.sizeHint().height() > area.height():
        need += area.verticalScrollBar().sizeHint().width()
    return need + 2 * area.frameWidth()


def _floor(widget):
    """How narrow fit_panel() may make another part of the splitter: a
    scroll panel keeps what it needs itself, anything else its minimum."""
    if isinstance(widget, QScrollArea) and widget.widget() is not None:
        return needed_width(widget)
    return max(widget.minimumSizeHint().width(), widget.minimumWidth())


def _available_width(window):
    screen = window.screen() if hasattr(window, 'screen') else None
    screen = screen or QApplication.primaryScreen()
    return screen.availableGeometry().width() if screen is not None else window.width()


def _keep_on_screen(window):
    """Move a window that a wider size pushed past the screen's right edge
    back onto the screen."""
    screen = window.screen() if hasattr(window, 'screen') else None
    screen = screen or QApplication.primaryScreen()
    if screen is None:
        return
    avail = screen.availableGeometry()
    frame = window.frameGeometry()
    if frame.right() > avail.right():
        window.move(max(avail.left(), window.x() - (frame.right() - avail.right())),
                    window.y())


def fit_panel(area):
    """Make every scroll panel of the horizontal splitter that holds `area`
    wide enough for its whole panel (all of them at once, measured before
    anything moves): the room comes first from the other parts of the
    splitter (down to their minimum), then from a wider window (at most as
    wide as the screen). Returns the pixels still missing (0 = everything
    fits; more only on a screen too small for the window)."""
    try:
        splitter = area.parentWidget()
        if not isinstance(splitter, QSplitter) or splitter.orientation() != Qt.Horizontal \
                or not area.isVisible() or getattr(splitter, '_panels_fitted', False):
            return 0
        splitter._panels_fitted = True
        n = splitter.count()
        parts = [splitter.widget(i) for i in range(n)]
        panel = [isinstance(w, QScrollArea) and w.widget() is not None and w.isVisible()
                 for w in parts]
        floors = [needed_width(w) if is_panel else (_floor(w) if w.isVisible() else 0)
                  for w, is_panel in zip(parts, panel)]
        sizes = splitter.sizes()
        if all(sizes[i] >= floors[i] for i in range(n) if panel[i]):
            return 0
        total = sum(sizes)
        missing = sum(floors) - total
        if missing > 0:
            window = area.window()
            grow = min(missing, max(0, _available_width(window) - window.width()))
            if grow > 0:
                window.resize(window.width() + grow, window.height())
                _keep_on_screen(window)
                QApplication.processEvents()
                sizes = splitter.sizes()
                total = sum(sizes)
                missing = sum(floors) - total
        # every scroll panel gets what it needs; the room comes from every
        # part (panel or not) in proportion to what it has above its minimum
        new = [max(sizes[i], floors[i]) if panel[i] else sizes[i] for i in range(n)]
        excess = sum(new) - total
        others = [i for i in range(n) if new[i] > floors[i]]
        room = sum(new[i] - floors[i] for i in others)
        if excess > 0 and room > 0:
            cut = min(excess, room)
            for i in others:
                new[i] -= int(cut * (new[i] - floors[i]) / room)
            excess = sum(new) - total
        if excess > 0:                  # a screen too small: the panels share the lack
            shares = [i for i in range(n) if panel[i]]
            for i in shares:
                new[i] -= -(-excess // len(shares))
        splitter.setSizes(new)
        return max(0, missing)
    except RuntimeError:                       # the window was closed meanwhile
        return 0


def no_collapse(splitter, min_size=None):
    """Keep every part of `splitter` visible while dragging: no collapsing to
    0, and (optionally) at least `min_size` pixels along the splitter's
    direction for parts that allow less. Parts can still be hidden on
    purpose with setVisible(False)."""
    splitter.setChildrenCollapsible(False)
    for i in range(splitter.count()):
        splitter.setCollapsible(i, False)
        if min_size:
            w = splitter.widget(i)
            if splitter.orientation() == Qt.Horizontal:
                if w.minimumWidth() < min_size:
                    w.setMinimumWidth(min_size)
            elif w.minimumHeight() < min_size:
                w.setMinimumHeight(min_size)
    return splitter


__all__ = ['scrollable_panel', 'no_collapse', 'fit_panel', 'fit_on_first_show', 'needed_width',
           'QSplitter']
