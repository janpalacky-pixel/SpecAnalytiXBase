# src/views/icons.py
"""Small icons for buttons and menu entries, as in MeltAnalytiX: the standard
icons of Windows / Qt (folder, disk, arrows, list, ...) and one drawn here,
the green "play" triangle of the Run buttons."""

from PyQt5.QtCore import QPointF, QRectF, Qt
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


def table_icon(size=16):
    """A small table (grid) for the Data table."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setPen(QColor('#3B5B8C'))
    p.setBrush(QColor('#FFFFFF'))
    m = 2
    w = size - 2 * m - 1
    p.drawRect(m, m, w, w)
    p.fillRect(m + 1, m + 1, w - 1, w // 3 - 1, QColor('#9DB7DD'))       # header row
    for k in (1, 2):
        y = m + k * w // 3
        p.drawLine(m, y, m + w, y)
        x = m + k * w // 3
        p.drawLine(x, m, x, m + w)
    p.end()
    return QIcon(pix)


def help_button(tooltip):
    """The small orange '?' of the program's context help."""
    from PyQt5.QtWidgets import QPushButton
    btn = QPushButton('?')
    btn.setFixedSize(24, 24)
    btn.setAutoDefault(False)
    btn.setToolTip(tooltip)
    btn.setStyleSheet(
        'QPushButton { background-color:#F57C00; color:white; font-weight:bold; border:none; '
        'border-radius:4px; }'
        'QPushButton:hover { background-color:#E65100; }'
        'QPushButton:pressed { background-color:#BF360C; }')
    return btn


def plot_icon(size=16):
    """A small plot (axes and a curve) for 'Copy plot to clipboard'."""
    from PyQt5.QtGui import QPainterPath, QPen
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor('#555555'), 1.2))
    p.drawLine(2, 2, 2, size - 2)
    p.drawLine(2, size - 2, size - 1, size - 2)
    path = QPainterPath(QPointF(3, size - 4))
    path.cubicTo(QPointF(6, size - 4), QPointF(7, 3), QPointF(9, 3))
    path.cubicTo(QPointF(11, 3), QPointF(12, size - 6), QPointF(size - 1, size - 6))
    p.setPen(QPen(QColor('#1F77B4'), 1.6))
    p.drawPath(path)
    p.end()
    return QIcon(pix)


def copy_icon(size=16):
    """Two overlapping sheets (copy to the clipboard)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#555555'))
    p.setBrush(QColor('#FFFFFF'))
    s = int(size * 0.6)
    p.drawRoundedRect(1, 1, s, s + 1, 1.5, 1.5)
    p.setBrush(QColor('#DCE8F7'))
    p.setPen(QColor('#3B5B8C'))
    p.drawRoundedRect(size - s - 2, size - s - 3, s, s + 1, 1.5, 1.5)
    p.end()
    return QIcon(pix)


def add_icon(size=16):
    """A green plus (add)."""
    from PyQt5.QtGui import QPen
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(RUN_GREEN), max(2.0, size / 7))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    m = size * 0.2
    p.drawLine(QPointF(size / 2, m), QPointF(size / 2, size - m))
    p.drawLine(QPointF(m, size / 2), QPointF(size - m, size / 2))
    p.end()
    return QIcon(pix)


def stop_icon(size=16):
    """A red square (stop)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor('#C62828'))
    m = size * 0.22
    p.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), 1.5, 1.5)
    p.end()
    return QIcon(pix)


def help_icon(size=16):
    """A blue circle with a white question mark (Help)."""
    from PyQt5.QtGui import QFont
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor('#1976D2'))
    p.drawEllipse(QRectF(0.5, 0.5, size - 1, size - 1))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(int(size * 0.72))
    p.setFont(font)
    p.setPen(QColor('#FFFFFF'))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, '?')
    p.end()
    return QIcon(pix)
