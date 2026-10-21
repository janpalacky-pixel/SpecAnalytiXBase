# src/views/icons.py
"""Small icons for buttons and menu entries, as in MeltAnalytiX: the standard
icons of Windows / Qt (folder, disk, arrows, list, ...) and one drawn here,
the green "play" triangle of the Run buttons."""

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PyQt5.QtWidgets import QApplication, QStyle

RUN_GREEN = '#2E7D32'


def standard(name, widget=None):
    """The standard icon `name` (e.g. 'SP_DialogSaveButton') of the style in use."""
    style = widget.style() if widget is not None else QApplication.style()
    return style.standardIcon(getattr(QStyle, name))


def run_icon(size=16):
    """A green triangle pointing right (start / run)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(RUN_GREEN))
    m = size * 0.18
    p.drawPolygon(QPolygonF([QPointF(m, m * 0.8), QPointF(size - m * 0.6, size / 2),
                             QPointF(m, size - m * 0.8)]))
    p.end()
    return QIcon(pix)
