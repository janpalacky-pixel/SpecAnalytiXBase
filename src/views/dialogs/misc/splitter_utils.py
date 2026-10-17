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
PCA Scores & Loadings, SVD Analysis or NMF."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QScrollArea, QSplitter

_QWIDGETSIZE_MAX = (1 << 24) - 1


def scrollable_panel(panel, min_width=240):
    """Return `panel` inside a frameless QScrollArea that the splitter can
    resize gradually. A fixed or maximum width set on the panel is released
    (narrow: the contents stay usable through the scroll bars; wide: they
    use the room)."""
    if panel.minimumWidth() == panel.maximumWidth() and panel.minimumWidth() > 0:
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
    return area


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


__all__ = ['scrollable_panel', 'no_collapse', 'QSplitter']
