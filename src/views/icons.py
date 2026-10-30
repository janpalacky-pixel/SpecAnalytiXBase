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


# ---------------------------------------------------------------------------
# The tool buttons under the menu bar (and their menu entries): small drawn
# icons, the same in every style. Drawn in a 16 x 16 grid and scaled, with a
# 32-pixel version for screens with large scaling.

def _tool_icon(draw):
    from PyQt5.QtGui import QPen
    icon = QIcon()
    for size in (16, 32):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(size / 16.0, size / 16.0)
        draw(p, QPen)
        p.end()
        icon.addPixmap(pix)
    return icon


def _curve(p, QPen, points, colour='#1F77B4', width=1.6, dash=False):
    from PyQt5.QtGui import QPainterPath
    path = QPainterPath(QPointF(*points[0]))
    for k in range(1, len(points) - 2, 3):
        path.cubicTo(QPointF(*points[k]), QPointF(*points[k + 1]), QPointF(*points[k + 2]))
    pen = QPen(QColor(colour), width)
    if dash:
        pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def _peak(p, QPen, top=3.0, base=13.0, colour='#1F77B4', width=1.6, left=1.0, right=15.0,
          mid=8.0, w=2.2):
    """A bell-shaped band: top at (mid, top), half width about w."""
    from PyQt5.QtGui import QPainterPath
    path = QPainterPath(QPointF(left, base))
    path.lineTo(QPointF(max(left, mid - 2.2 * w), base))
    path.cubicTo(QPointF(mid - 1.0 * w, base), QPointF(mid - 0.75 * w, top), QPointF(mid, top))
    path.cubicTo(QPointF(mid + 0.75 * w, top), QPointF(mid + 1.0 * w, base),
                 QPointF(min(right, mid + 2.2 * w), base))
    path.lineTo(QPointF(right, base))
    p.setPen(QPen(QColor(colour), width))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def data_range_icon():
    """A spectrum with two orange limits: the part kept between them."""
    def draw(p, QPen):
        p.fillRect(QRectF(0.5, 1, 4, 14), QColor('#E3E6EA'))
        p.fillRect(QRectF(11.5, 1, 4, 14), QColor('#E3E6EA'))
        _peak(p, QPen, top=3.5, base=12.5, w=2.0)
        pen = QPen(QColor('#EF6C00'), 1.6)
        p.setPen(pen)
        p.drawLine(QPointF(4.5, 1.5), QPointF(4.5, 14.5))
        p.drawLine(QPointF(11.5, 1.5), QPointF(11.5, 14.5))
    return _tool_icon(draw)


def smoothing_icon():
    """A noisy line (grey) and the smooth one (blue)."""
    def draw(p, QPen):
        p.setPen(QPen(QColor('#9AA0A6'), 1.0))
        pts = [(1, 9), (2.5, 6), (4, 9.5), (5.5, 4.5), (7, 8), (8.5, 3.5), (10, 7.5),
               (11.5, 4), (13, 8.5), (15, 6)]
        for a, b in zip(pts, pts[1:]):
            p.drawLine(QPointF(*a), QPointF(*b))
        _curve(p, QPen, [(1, 9), (4, 7), (6, 5), (8, 5.5), (10, 6), (12, 6.5), (15, 6.5)],
               '#1F77B4', 1.8)
        p.setPen(QPen(QColor('#1F77B4'), 1.8))
        p.drawLine(QPointF(1, 13.5), QPointF(15, 13.5))
    return _tool_icon(draw)


def baseline_icon():
    """A band on a sloping background (red dashed line under it)."""
    def draw(p, QPen):
        _curve(p, QPen, [(1, 11), (4, 10.5), (6, 3), (8, 3), (10, 3), (12, 9), (15, 8)],
               '#1F77B4', 1.6)
        pen = QPen(QColor('#C62828'), 1.4)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(1, 12.5), QPointF(15, 9.5))
        p.setPen(QPen(QColor('#555555'), 1.0))
        p.drawLine(QPointF(1, 14.5), QPointF(15, 14.5))
    return _tool_icon(draw)


def normalization_icon():
    """Two bands of different height brought to the same top (green line)."""
    def draw(p, QPen):
        pen = QPen(QColor(RUN_GREEN), 1.4)
        p.setPen(pen)
        p.drawLine(QPointF(1, 3), QPointF(15, 3))
        _peak(p, QPen, top=3, base=14, colour='#1F77B4', left=0.5, right=10, mid=5, w=1.9)
        _peak(p, QPen, top=3, base=14, colour='#FF7F0E', left=6, right=15.5, mid=11, w=1.9)
    return _tool_icon(draw)


def peak_list_icon():
    """A band with a red dot on its top and a short list beside it."""
    def draw(p, QPen):
        _peak(p, QPen, top=5, base=14, left=0.5, right=10.5, mid=5.2, w=2.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#D62728'))
        p.drawEllipse(QPointF(5, 4.2), 1.9, 1.9)
        p.setPen(QPen(QColor('#555555'), 1.3))
        for y in (3.5, 7, 10.5):
            p.drawLine(QPointF(11.5, y), QPointF(15.5, y))
    return _tool_icon(draw)


def peak_fitting_icon():
    """A hump (dark) fitted by two bands (orange and green) under it."""
    def draw(p, QPen):
        _peak(p, QPen, top=6, base=14, colour='#FF7F0E', width=1.3, left=0.5, right=12, mid=6, w=2.0)
        _peak(p, QPen, top=8, base=14, colour=RUN_GREEN, width=1.3, left=4, right=15.5, mid=10.2, w=2.0)
        _curve(p, QPen, [(0.5, 14), (2.5, 14), (3.5, 5), (6, 5), (7.5, 5), (8.5, 6.5),
                         (10.2, 6.5), (12, 6.5), (13, 14), (15.5, 14)], '#C62828', 1.5)
    return _tool_icon(draw)


def copy_plot_icon():
    """A small plot on a sheet, with a second sheet behind it (copy the plot)."""
    def draw(p, QPen):
        p.setPen(QColor('#555555'))
        p.setBrush(QColor('#FFFFFF'))
        p.drawRoundedRect(QRectF(0.5, 0.5, 9, 10), 1.2, 1.2)
        p.setPen(QColor('#3B5B8C'))
        p.setBrush(QColor('#F4F8FD'))
        p.drawRoundedRect(QRectF(4.5, 4.5, 11, 11), 1.2, 1.2)
        p.setPen(QPen(QColor('#555555'), 1.0))
        p.drawLine(QPointF(6.5, 6.5), QPointF(6.5, 13.5))
        p.drawLine(QPointF(6.5, 13.5), QPointF(14.5, 13.5))
        _curve(p, QPen, [(7, 12.5), (9, 12.5), (9.5, 7), (10.5, 7), (11.5, 7), (12, 11),
                         (14.5, 11)], '#1F77B4', 1.4)
    return _tool_icon(draw)


# ---------------------------------------------------------------------------
# Icons of the other menu entries (Spectra processing, Analysis &
# Visualization), in the same style.
BLUE, ORANGE, GREEN, RED, GREY, DARK = ('#1F77B4', '#FF7F0E', RUN_GREEN, '#C62828', '#9AA0A6',
                                        '#455A64')


def _line(p, QPen, a, b, colour=DARK, width=1.3, dash=False):
    pen = QPen(QColor(colour), width)
    if dash:
        pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(*a), QPointF(*b))


def _poly(p, QPen, pts, colour=BLUE, width=1.5):
    p.setPen(QPen(QColor(colour), width))
    for a, b in zip(pts, pts[1:]):
        p.drawLine(QPointF(*a), QPointF(*b))


def _dot(p, xy, r=1.6, colour=RED):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(colour))
    p.drawEllipse(QPointF(*xy), r, r)
    p.setBrush(Qt.NoBrush)


def _box(p, QPen, rect, fill, edge=DARK, width=1.0, radius=1.0):
    p.setPen(QPen(QColor(edge), width))
    p.setBrush(QColor(fill))
    p.drawRoundedRect(QRectF(*rect), radius, radius)
    p.setBrush(Qt.NoBrush)


def manual_baseline_icon():
    """A band; the baseline drawn through clicked points (red dots)."""
    def draw(p, QPen):
        _curve(p, QPen, [(1, 11), (4, 10.5), (6, 3), (8, 3), (10, 3), (12, 9), (15, 8)])
        _line(p, QPen, (1, 12.5), (15, 9.5), RED, 1.2, dash=True)
        for xy in ((2, 12.3), (8, 11.0), (14, 9.7)):
            _dot(p, xy, 1.7)
    return _tool_icon(draw)


def snip_baseline_icon():
    """A band; the background (red) follows the bottom of the spectrum."""
    def draw(p, QPen):
        _curve(p, QPen, [(1, 10), (4, 10), (6, 3), (8, 3), (10, 3), (12, 9), (15, 7)])
        _curve(p, QPen, [(1, 12), (5, 11.5), (10, 11.5), (15, 9)], RED, 1.4)
        _line(p, QPen, (1, 14.5), (15, 14.5), '#555555', 1.0)
    return _tool_icon(draw)


def svd_background_icon():
    """A band and, faint, the components of the background (grey)."""
    def draw(p, QPen):
        _curve(p, QPen, [(1, 6), (5, 7), (10, 7), (15, 5)], GREY, 1.0)
        _curve(p, QPen, [(1, 9), (5, 8), (10, 10), (15, 9)], GREY, 1.0)
        _curve(p, QPen, [(1, 11), (4, 10.5), (6, 2.5), (8, 2.5), (10, 2.5), (12, 9.5), (15, 8)])
        _line(p, QPen, (1, 13), (15, 11), RED, 1.3, dash=True)
    return _tool_icon(draw)


def fft_denoising_icon():
    """Frequency bars, the high ones (right) cut off by a red line."""
    def draw(p, QPen):
        for k, h in enumerate((11, 8, 6, 4.5, 3.5, 3, 2.6, 2.3)):
            colour = BLUE if k < 4 else GREY
            p.fillRect(QRectF(1 + k * 1.8, 14.5 - h, 1.2, h), QColor(colour))
        _line(p, QPen, (8.6, 1), (8.6, 15), RED, 1.4)
    return _tool_icon(draw)


def combine_spectra_icon():
    """Two spectra (blue, orange) joined into one (dark)."""
    def draw(p, QPen):
        _poly(p, QPen, [(1, 4), (3, 3), (5, 5), (7, 7)], BLUE, 1.6)
        _poly(p, QPen, [(1, 12), (3, 13), (5, 11), (7, 9)], ORANGE, 1.6)
        _poly(p, QPen, [(7, 8), (9, 6), (11, 10), (13, 5), (15, 8)], DARK, 1.8)
    return _tool_icon(draw)


def interactive_subtraction_icon():
    """A spectrum minus another one (minus sign)."""
    def draw(p, QPen):
        _peak(p, QPen, top=2.5, base=8, left=0.5, right=10, mid=4.5, w=1.6)
        _peak(p, QPen, top=9.5, base=14.5, colour=ORANGE, left=0.5, right=10, mid=6, w=1.6)
        _line(p, QPen, (11.5, 8), (15.5, 8), RED, 2.0)
    return _tool_icon(draw)


def x_alignment_icon():
    """Two peaks moved onto the same position (arrow)."""
    def draw(p, QPen):
        _peak(p, QPen, top=2, base=7, left=0.5, right=15.5, mid=9, w=1.6)
        _peak(p, QPen, top=9, base=14.5, colour=ORANGE, left=0.5, right=15.5, mid=5, w=1.6)
        pen = QPen(QColor(RED), 1.3)
        p.setPen(pen)
        p.drawLine(QPointF(5.5, 8), QPointF(9, 8))
        p.drawLine(QPointF(9, 8), QPointF(7.4, 6.8))
        p.drawLine(QPointF(9, 8), QPointF(7.4, 9.2))
    return _tool_icon(draw)


def svd_interpolation_icon():
    """Measured points with a gap, filled by a curve (dashed)."""
    def draw(p, QPen):
        _curve(p, QPen, [(1, 12), (4, 12), (6, 4), (8, 4), (10, 4), (12, 11), (15, 11)], GREY,
               1.0)
        for x, y in ((1.5, 12), (3.5, 11.6), (5, 8.5), (11.5, 9.8), (13.5, 11), (15, 11)):
            _dot(p, (x, y), 1.4, BLUE)
        _curve(p, QPen, [(5, 8.5), (6.5, 3), (9.5, 3), (11.5, 9.8)], RED, 1.3, dash=True)
    return _tool_icon(draw)


def spectral_calculator_icon():
    """A calculator."""
    def draw(p, QPen):
        _box(p, QPen, (2.5, 0.8, 11, 14.4), '#ECEFF1', DARK, 1.0, 1.5)
        p.fillRect(QRectF(4, 2.3, 8, 3), QColor('#C8E6C9'))
        for r in range(3):
            for c in range(3):
                colour = ORANGE if c == 2 else '#78909C'
                p.fillRect(QRectF(4 + c * 3, 6.6 + r * 2.8, 2, 1.9), QColor(colour))
    return _tool_icon(draw)


def cd_conversion_icon():
    """A CD band up and down, with up/down arrows (units)."""
    def draw(p, QPen):
        _line(p, QPen, (0.5, 8), (12, 8), GREY, 0.8)
        _curve(p, QPen, [(0.5, 8), (2.5, 8), (3, 2.5), (4.5, 2.5), (6, 2.5), (6, 8), (6.5, 8)])
        _curve(p, QPen, [(6.5, 8), (7, 8), (7.5, 13.5), (9, 13.5), (10.5, 13.5), (11, 8),
                         (12, 8)])
        p.setPen(QPen(QColor(RED), 1.3))
        p.drawLine(QPointF(14, 2.5), QPointF(14, 13.5))
        for y, d in ((2.5, 1), (13.5, -1)):
            p.drawLine(QPointF(14, y), QPointF(12.6, y + 1.6 * d))
            p.drawLine(QPointF(14, y), QPointF(15.4, y + 1.6 * d))
    return _tool_icon(draw)


def x_unit_conversion_icon():
    """An x axis with ticks and a two-way arrow (nm <-> cm-1)."""
    def draw(p, QPen):
        _line(p, QPen, (1, 11), (15, 11), DARK, 1.3)
        for x in (2, 5, 8, 11, 14):
            _line(p, QPen, (x, 11), (x, 13.5), DARK, 1.0)
        p.setPen(QPen(QColor(RED), 1.4))
        p.drawLine(QPointF(2, 5), QPointF(14, 5))
        for x, d in ((2, 1), (14, -1)):
            p.drawLine(QPointF(x, 5), QPointF(x + 2 * d, 3.4))
            p.drawLine(QPointF(x, 5), QPointF(x + 2 * d, 6.6))
    return _tool_icon(draw)


def mean_centering_icon():
    """Spectra around their mean (dashed line through the middle)."""
    def draw(p, QPen):
        _line(p, QPen, (0.5, 8), (15.5, 8), GREY, 1.0, dash=True)
        _curve(p, QPen, [(0.5, 8), (3, 8), (4, 3), (6, 3), (8, 3), (8, 8), (9, 8)], BLUE, 1.5)
        _curve(p, QPen, [(9, 8), (10, 8), (11, 13), (12.5, 13), (14, 13), (14, 8), (15.5, 8)],
               ORANGE, 1.5)
    return _tool_icon(draw)


def spike_removal_icon():
    """A spectrum with a sharp red spike, crossed out."""
    def draw(p, QPen):
        _curve(p, QPen, [(0.5, 12), (4, 12), (5, 8), (7, 8), (9, 8), (10, 12), (15.5, 12)])
        _poly(p, QPen, [(10.5, 12), (11.5, 1.5), (12.5, 12)], RED, 1.5)
        _line(p, QPen, (9, 4), (14, 9), DARK, 1.4)
    return _tool_icon(draw)


def cosmic_ray_icon():
    """A red star (a cosmic ray) on a spectrum."""
    def draw(p, QPen):
        _curve(p, QPen, [(0.5, 13), (4, 13), (5, 9), (7, 9), (9, 9), (10, 13), (15.5, 13)])
        p.setPen(QPen(QColor(RED), 1.4))
        cx, cy = 11, 4.5
        for dx, dy in ((0, 3.5), (3.5, 0), (2.4, 2.4), (2.4, -2.4)):
            p.drawLine(QPointF(cx - dx, cy - dy), QPointF(cx + dx, cy + dy))
    return _tool_icon(draw)


def resolution_icon():
    """A broad band (grey) made narrow (blue)."""
    def draw(p, QPen):
        _peak(p, QPen, top=6, base=14, colour=GREY, width=1.3, left=0.5, right=15.5, mid=8, w=3.4)
        _peak(p, QPen, top=1.8, base=14, colour=BLUE, width=1.7, left=0.5, right=15.5, mid=8,
              w=1.2)
    return _tool_icon(draw)


def pipeline_icon():
    """Three steps in a row (boxes and arrows)."""
    def draw(p, QPen):
        for x in (0.5, 6, 11.5):
            _box(p, QPen, (x, 5, 4, 6), '#DCE8F7', '#3B5B8C', 1.0, 1.0)
        p.setPen(QPen(QColor(DARK), 1.2))
        for x in (4.5, 10):
            p.drawLine(QPointF(x, 8), QPointF(x + 1.5, 8))
    return _tool_icon(draw)


def run_pipeline_icon():
    """The steps and a green Run triangle."""
    def draw(p, QPen):
        for x in (0.5, 5.5):
            _box(p, QPen, (x, 2, 4, 5), '#DCE8F7', '#3B5B8C', 1.0, 1.0)
        p.setPen(QPen(QColor(DARK), 1.2))
        p.drawLine(QPointF(4.5, 4.5), QPointF(5.5, 4.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(RUN_GREEN))
        p.drawPolygon(QPolygonF([QPointF(8, 8.5), QPointF(15, 12), QPointF(8, 15.5)]))
    return _tool_icon(draw)


def save_pipeline_icon():
    """The steps and a disk (save them)."""
    def draw(p, QPen):
        for x in (0.5, 5.5):
            _box(p, QPen, (x, 2, 4, 5), '#DCE8F7', '#3B5B8C', 1.0, 1.0)
        p.setPen(QPen(QColor(DARK), 1.2))
        p.drawLine(QPointF(4.5, 4.5), QPointF(5.5, 4.5))
        _box(p, QPen, (8.5, 8, 7, 7), '#3B5B8C', '#3B5B8C', 1.0, 1.0)
        p.fillRect(QRectF(10, 8.5, 4, 2.4), QColor('#FFFFFF'))
        p.fillRect(QRectF(10, 12, 4, 2.5), QColor('#B0BEC5'))
    return _tool_icon(draw)


def svd_analysis_icon():
    """A data matrix split into three (U, S, V): the middle one diagonal."""
    def draw(p, QPen):
        _box(p, QPen, (0.5, 2, 4, 12), '#DCE8F7', '#3B5B8C')
        _box(p, QPen, (6, 4.5, 4.5, 7), '#FFFFFF', '#3B5B8C')
        for xy in ((7.2, 6), (8.25, 8), (9.3, 10)):
            _dot(p, xy, 1.0, RED)
        _box(p, QPen, (11.5, 5, 4, 6), '#FFE0B2', '#E65100')
    return _tool_icon(draw)


def pca_icon():
    """Scores as dots with the first two components (arrows)."""
    def draw(p, QPen):
        for xy in ((4, 11), (5.5, 9.5), (7, 9), (8, 7.5), (9.5, 6.5), (11, 5), (6, 7), (10, 8.5)):
            _dot(p, xy, 1.2, BLUE)
        p.setPen(QPen(QColor(RED), 1.4))
        p.drawLine(QPointF(2, 13), QPointF(14, 3))
        p.setPen(QPen(QColor(GREEN), 1.4))
        p.drawLine(QPointF(5, 4), QPointF(11, 12))
    return _tool_icon(draw)


def nmf_icon():
    """Two components, both above zero."""
    def draw(p, QPen):
        _line(p, QPen, (0.5, 14.5), (15.5, 14.5), DARK, 1.0)
        _peak(p, QPen, top=3, base=14, colour=ORANGE, left=0.5, right=15.5, mid=5, w=1.8)
        _curve(p, QPen, [(0.5, 14), (6, 14), (9, 9), (11, 7), (13, 6), (14, 6), (15.5, 6)],
               GREEN, 1.5)
    return _tool_icon(draw)


def mcr_icon():
    """Two components (orange, green) and a circular arrow (repeated steps)."""
    def draw(p, QPen):
        _peak(p, QPen, top=5, base=14, colour=ORANGE, left=0.5, right=10, mid=4, w=1.6)
        _peak(p, QPen, top=8, base=14, colour=GREEN, left=2, right=11, mid=7.5, w=1.6)
        p.setPen(QPen(QColor(BLUE), 1.4))
        p.drawArc(QRectF(10, 1, 5.5, 5.5), 30 * 16, 280 * 16)
        p.drawLine(QPointF(15.2, 2.6), QPointF(15.4, 4.6))
    return _tool_icon(draw)


def cluster_icon():
    """Two groups of dots, each in a ring."""
    def draw(p, QPen):
        for xy in ((3.5, 4), (5, 6), (3, 6.5), (5.5, 3.5)):
            _dot(p, xy, 1.2, BLUE)
        for xy in ((10.5, 11), (12.5, 10), (11, 13), (13, 12.5)):
            _dot(p, xy, 1.2, ORANGE)
        p.setPen(QPen(QColor(BLUE), 1.0))
        p.drawEllipse(QPointF(4.3, 5), 3.4, 3.4)
        p.setPen(QPen(QColor(ORANGE), 1.0))
        p.drawEllipse(QPointF(11.8, 11.6), 3.4, 3.4)
    return _tool_icon(draw)


def som_icon():
    """A small map of nodes in colours."""
    def draw(p, QPen):
        colours = ('#1F77B4', '#4C9BD6', '#9DC9EC', '#4C9BD6', '#FFB74D', '#FF7F0E',
                   '#9DC9EC', '#FFB74D', '#E65100')
        for k, c in enumerate(colours):
            r, col = divmod(k, 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(3 + col * 5 + (2.5 if r % 2 else 0) * 0, 3 + r * 5), 2.2, 2.2)
    return _tool_icon(draw)


def map2d_icon():
    """A heat map (grid of colours)."""
    def draw(p, QPen):
        grid = (('#2C7BB6', '#ABD9E9', '#FFFFBF', '#FDAE61'),
                ('#ABD9E9', '#FFFFBF', '#FDAE61', '#D7191C'),
                ('#FFFFBF', '#FDAE61', '#D7191C', '#FDAE61'),
                ('#ABD9E9', '#FFFFBF', '#FDAE61', '#FFFFBF'))
        for r, row in enumerate(grid):
            for c, colour in enumerate(row):
                p.fillRect(QRectF(1 + c * 3.5, 1 + r * 3.5, 3.5, 3.5), QColor(colour))
        p.setPen(QPen(QColor(DARK), 0.8))
        p.drawRect(QRectF(1, 1, 14, 14))
    return _tool_icon(draw)


def correlation2d_icon():
    """Contours on both sides of the diagonal."""
    def draw(p, QPen):
        _line(p, QPen, (1, 15), (15, 1), GREY, 0.8, dash=True)
        p.setPen(QPen(QColor(RED), 1.2))
        p.drawEllipse(QPointF(5, 5), 2.5, 2.5)
        p.drawEllipse(QPointF(11, 11), 2.5, 2.5)
        p.setPen(QPen(QColor(BLUE), 1.2))
        p.drawEllipse(QPointF(11, 5), 2.2, 2.2)
        p.drawEllipse(QPointF(5, 11), 2.2, 2.2)
    return _tool_icon(draw)


def pls_icon():
    """Predicted against measured: dots along a line."""
    def draw(p, QPen):
        _line(p, QPen, (1, 1), (1, 15), DARK, 1.0)
        _line(p, QPen, (1, 15), (15, 15), DARK, 1.0)
        _line(p, QPen, (2.5, 13.5), (14.5, 2), RED, 1.3)
        for xy in ((4, 11), (6, 10.5), (7.5, 8), (9.5, 7.5), (11, 5), (13, 4)):
            _dot(p, xy, 1.2, BLUE)
    return _tool_icon(draw)


def band_ratio_icon():
    """Two bands (A, B) and a fraction line between them."""
    def draw(p, QPen):
        _peak(p, QPen, top=1.5, base=6.5, left=0.5, right=15.5, mid=8, w=1.6)
        _line(p, QPen, (2, 8), (14, 8), DARK, 1.4)
        _peak(p, QPen, top=10, base=14.5, colour=ORANGE, left=0.5, right=15.5, mid=8, w=1.6)
    return _tool_icon(draw)


def reference_matching_icon():
    """A spectrum over a reference (grey) and a green tick."""
    def draw(p, QPen):
        _curve(p, QPen, [(0.5, 13), (2, 13), (3.5, 5), (5, 5), (6.5, 5), (7, 11), (9, 11)],
               GREY, 2.6)
        _curve(p, QPen, [(0.5, 13), (2, 13), (3.5, 5), (5, 5), (6.5, 5), (7, 11), (9, 11)],
               BLUE, 1.2)
        p.setPen(QPen(QColor(GREEN), 2.0))
        p.drawLine(QPointF(9.5, 9), QPointF(11.5, 12))
        p.drawLine(QPointF(11.5, 12), QPointF(15.5, 4))
    return _tool_icon(draw)


def melting_curve_icon():
    """A sigmoid (folded -> unfolded) with its midpoint."""
    def draw(p, QPen):
        _curve(p, QPen, [(0.5, 3), (5, 3), (6.5, 3.5), (8, 8), (9.5, 12.5), (11, 13),
                         (15.5, 13)], RED, 1.6)
        _line(p, QPen, (8, 1), (8, 15), GREY, 0.9, dash=True)
        _dot(p, (8, 8), 1.7, BLUE)
    return _tool_icon(draw)


def isosbestic_icon():
    """Spectra crossing in one point."""
    def draw(p, QPen):
        _poly(p, QPen, [(1, 3), (8, 8), (15, 13)], BLUE, 1.4)
        _poly(p, QPen, [(1, 6), (8, 8), (15, 10)], ORANGE, 1.4)
        _poly(p, QPen, [(1, 12), (8, 8), (15, 4)], GREEN, 1.4)
        _dot(p, (8, 8), 1.9, RED)
    return _tool_icon(draw)


def kinetics_icon():
    """Measured points following an exponential decay."""
    def draw(p, QPen):
        _line(p, QPen, (1, 1), (1, 15), DARK, 1.0)
        _line(p, QPen, (1, 15), (15, 15), DARK, 1.0)
        _curve(p, QPen, [(2, 2.5), (5, 9), (8, 12), (15, 13)], RED, 1.4)
        for xy in ((2.5, 3.5), (4.5, 7.5), (7, 10.5), (10, 12), (13, 13)):
            _dot(p, xy, 1.2, BLUE)
    return _tool_icon(draw)


def qc_outlier_icon():
    """Dots inside a dashed band, one red dot outside."""
    def draw(p, QPen):
        _line(p, QPen, (1, 5), (15, 5), GREY, 1.0, dash=True)
        _line(p, QPen, (1, 11), (15, 11), GREY, 1.0, dash=True)
        for xy in ((2.5, 8), (5, 7), (7.5, 9), (12.5, 8.5), (15, 7.5)):
            _dot(p, xy, 1.2, BLUE)
        _dot(p, (10, 2), 1.8, RED)
    return _tool_icon(draw)


def group_statistics_icon():
    """Two box plots (two groups compared)."""
    def draw(p, QPen):
        for x, top, low, mid, fill, edge in ((2, 3, 10, 7, '#DCE8F7', BLUE),
                                             (9.5, 6, 13, 9.5, '#FFE0B2', ORANGE)):
            _line(p, QPen, (x + 2.2, top - 2), (x + 2.2, low + 2), edge, 1.0)
            _box(p, QPen, (x, top, 4.4, low - top), fill, edge, 1.0, 0.5)
            _line(p, QPen, (x, mid), (x + 4.4, mid), edge, 1.4)
    return _tool_icon(draw)


def mixture_icon():
    """A pie: how much of each known component."""
    def draw(p, QPen):
        rect = QRectF(1.5, 1.5, 13, 13)
        p.setPen(QPen(QColor('#FFFFFF'), 0.8))
        for start, span, colour in ((90, 200, BLUE), (290, 110, ORANGE), (40, 50, GREEN)):
            p.setBrush(QColor(colour))
            p.drawPie(rect, start * 16, span * 16)
        p.setBrush(Qt.NoBrush)
    return _tool_icon(draw)


def import_icon():
    """A folder with a spectrum coming in (Import data)."""
    def draw(p, QPen):
        _box(p, QPen, (0.5, 5, 15, 10), '#F6C451', '#B8860B', 1.0, 1.2)
        p.fillRect(QRectF(0.5, 3.5, 6, 2.5), QColor('#F6C451'))
        _curve(p, QPen, [(2, 13), (4, 13), (5.5, 7.5), (7, 7.5), (8.5, 7.5), (10, 13), (14, 13)],
               BLUE, 1.5)
    return _tool_icon(draw)


# ---------------------------------------------------------------------------
# Icons of the Help menu.

def book_icon():
    """An open book (User Guide)."""
    def draw(p, QPen):
        _box(p, QPen, (0.8, 3, 7, 10.5), '#E3F2FD', '#1565C0', 1.0, 0.8)
        _box(p, QPen, (8.2, 3, 7, 10.5), '#E3F2FD', '#1565C0', 1.0, 0.8)
        for y in (5.5, 7.5, 9.5):
            _line(p, QPen, (2.2, y), (6.5, y), '#90A4AE', 0.8)
            _line(p, QPen, (9.5, y), (13.8, y), '#90A4AE', 0.8)
    return _tool_icon(draw)


def quick_start_icon():
    """A green Run triangle on a page (start quickly)."""
    def draw(p, QPen):
        _box(p, QPen, (1, 1, 10, 13.5), '#FFFFFF', DARK, 1.0, 0.8)
        for y in (4, 6.5, 9):
            _line(p, QPen, (3, y), (8.5, y), '#90A4AE', 0.9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(RUN_GREEN))
        p.drawPolygon(QPolygonF([QPointF(8, 8), QPointF(15.5, 11.8), QPointF(8, 15.6)]))
    return _tool_icon(draw)


def whats_new_icon():
    """A yellow star."""
    def draw(p, QPen):
        import math
        pts = []
        for k in range(10):
            r = 7.2 if k % 2 == 0 else 3.1
            a = math.pi / 2 + k * math.pi / 5
            pts.append(QPointF(8 + r * math.cos(a), 8.6 - r * math.sin(a)))
        p.setPen(QPen(QColor('#E65100'), 0.9))
        p.setBrush(QColor('#FFC107'))
        p.drawPolygon(QPolygonF(pts))
    return _tool_icon(draw)


def keyboard_icon():
    """A keyboard."""
    def draw(p, QPen):
        _box(p, QPen, (0.5, 3.5, 15, 9.5), '#ECEFF1', DARK, 1.0, 1.2)
        for r in range(2):
            for c in range(5):
                p.fillRect(QRectF(2 + c * 2.5, 5.2 + r * 2.4, 1.8, 1.6), QColor('#607D8B'))
        p.fillRect(QRectF(4.5, 10, 7, 1.6), QColor('#607D8B'))
    return _tool_icon(draw)


def installation_icon():
    """A box with an arrow into it (install)."""
    def draw(p, QPen):
        _box(p, QPen, (1.5, 8, 13, 7), '#D7B98E', '#8D6E63', 1.0, 0.8)
        _line(p, QPen, (1.5, 10.5), (14.5, 10.5), '#8D6E63', 0.8)
        p.setPen(QPen(QColor(BLUE), 1.8))
        p.drawLine(QPointF(8, 0.8), QPointF(8, 8.5))
        p.drawLine(QPointF(8, 8.5), QPointF(5.2, 5.6))
        p.drawLine(QPointF(8, 8.5), QPointF(10.8, 5.6))
    return _tool_icon(draw)


def developer_icon():
    """</> (the program's code)."""
    def draw(p, QPen):
        p.setPen(QPen(QColor('#6A1B9A'), 1.6))
        p.drawLine(QPointF(5, 4), QPointF(1.5, 8))
        p.drawLine(QPointF(1.5, 8), QPointF(5, 12))
        p.drawLine(QPointF(11, 4), QPointF(14.5, 8))
        p.drawLine(QPointF(14.5, 8), QPointF(11, 12))
        p.setPen(QPen(QColor(DARK), 1.4))
        p.drawLine(QPointF(9.3, 3), QPointF(6.7, 13))
    return _tool_icon(draw)


def datasets_icon():
    """A flask (test data)."""
    def draw(p, QPen):
        p.setPen(QPen(QColor(DARK), 1.1))
        p.setBrush(QColor('#FFFFFF'))
        p.drawPolygon(QPolygonF([QPointF(6, 1), QPointF(10, 1), QPointF(10, 5.5),
                                 QPointF(14.5, 14.5), QPointF(1.5, 14.5), QPointF(6, 5.5)]))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#4FC3F7'))
        p.drawPolygon(QPolygonF([QPointF(4, 9.5), QPointF(12, 9.5), QPointF(14, 13.8),
                                 QPointF(2, 13.8)]))
        p.setBrush(Qt.NoBrush)
    return _tool_icon(draw)


def data_file_icon():
    """A page with a spectrum (one test data file)."""
    def draw(p, QPen):
        p.setPen(QPen(QColor(DARK), 1.0))
        p.setBrush(QColor('#FFFFFF'))
        p.drawPolygon(QPolygonF([QPointF(2.5, 0.8), QPointF(10, 0.8), QPointF(13.5, 4.3),
                                 QPointF(13.5, 15.2), QPointF(2.5, 15.2)]))
        p.setBrush(Qt.NoBrush)
        _curve(p, QPen, [(3.5, 12.5), (5.5, 12.5), (6.5, 6), (8, 6), (9.5, 6), (10.5, 12.5),
                         (12.5, 12.5)], BLUE, 1.3)
    return _tool_icon(draw)


def download_icon():
    """An arrow down onto a line (download)."""
    def draw(p, QPen):
        p.setPen(QPen(QColor(RUN_GREEN), 2.0))
        p.drawLine(QPointF(8, 1), QPointF(8, 10))
        p.drawLine(QPointF(8, 10), QPointF(4.5, 6.5))
        p.drawLine(QPointF(8, 10), QPointF(11.5, 6.5))
        _line(p, QPen, (2, 14), (14, 14), DARK, 1.6)
    return _tool_icon(draw)


def folder_icon():
    """A yellow folder."""
    def draw(p, QPen):
        p.fillRect(QRectF(0.5, 3, 6, 2.5), QColor('#F6C451'))
        _box(p, QPen, (0.5, 4.5, 15, 10), '#F6C451', '#B8860B', 1.0, 1.2)
    return _tool_icon(draw)


def group_icon():
    """Three people (our group)."""
    def draw(p, QPen):
        for x, c in ((3.5, '#90CAF9'), (12.5, '#90CAF9'), (8, '#1E88E5')):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(x, 5 if x == 8 else 6), 2.2, 2.2)
            p.drawChord(QRectF(x - 3.6, (9 if x == 8 else 10), 7.2, 9), 0, 180 * 16)
        p.setBrush(Qt.NoBrush)
    return _tool_icon(draw)


def institute_icon():
    """A building with columns."""
    def draw(p, QPen):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#546E7A'))
        p.drawPolygon(QPolygonF([QPointF(8, 0.8), QPointF(15.5, 5), QPointF(0.5, 5)]))
        p.setBrush(Qt.NoBrush)
        for x in (2.2, 5.6, 9.2, 12.6):
            p.fillRect(QRectF(x, 6, 1.6, 6.5), QColor('#78909C'))
        p.fillRect(QRectF(0.5, 13, 15, 2), QColor('#546E7A'))
    return _tool_icon(draw)


def license_icon():
    """A document with a seal."""
    def draw(p, QPen):
        _box(p, QPen, (1.5, 0.8, 11, 13.5), '#FFFFFF', DARK, 1.0, 0.8)
        for y in (3.5, 6, 8.5):
            _line(p, QPen, (3.5, y), (10.5, y), '#90A4AE', 0.9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#C62828'))
        p.drawEllipse(QPointF(11.5, 12), 3.2, 3.2)
        p.setBrush(Qt.NoBrush)
    return _tool_icon(draw)


def run_tests_icon():
    """A list with green ticks (the tests)."""
    def draw(p, QPen):
        for k, y in enumerate((3, 8, 13)):
            p.setPen(QPen(QColor(RUN_GREEN), 1.6))
            p.drawLine(QPointF(1, y), QPointF(2.6, y + 1.6))
            p.drawLine(QPointF(2.6, y + 1.6), QPointF(5.4, y - 1.6))
            _line(p, QPen, (7.5, y), (15, y), DARK, 1.3)
    return _tool_icon(draw)


def about_icon():
    """A blue circle with a white i."""
    def draw(p, QPen):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#1E88E5'))
        p.drawEllipse(QPointF(8, 8), 7.3, 7.3)
        p.setBrush(QColor('#FFFFFF'))
        p.drawEllipse(QPointF(8, 4.4), 1.3, 1.3)
        p.drawRoundedRect(QRectF(6.9, 6.6, 2.2, 6.4), 0.6, 0.6)
        p.setBrush(Qt.NoBrush)
    return _tool_icon(draw)


def synthetic_data_icon():
    """A smooth, perfect band with a sparkle (made by the computer)."""
    def draw(p, QPen):
        _peak(p, QPen, top=5, base=14, colour='#7B1FA2', width=1.6, left=0.5, right=13, mid=6.5,
              w=2.0)
        p.setPen(QPen(QColor('#F9A825'), 1.4))
        cx, cy = 12.8, 3.2
        p.drawLine(QPointF(cx, cy - 2.6), QPointF(cx, cy + 2.6))
        p.drawLine(QPointF(cx - 2.6, cy), QPointF(cx + 2.6, cy))
    return _tool_icon(draw)


def measured_data_icon():
    """A noisy measured band (real data)."""
    def draw(p, QPen):
        pts = [(0.5, 13.5), (2, 12.8), (3, 13.6), (4, 11.5), (5, 8), (5.8, 5.5), (6.6, 3.4),
               (7.4, 4.6), (8.2, 3), (9, 6), (9.8, 9.5), (10.8, 12), (12, 12.8), (13, 12),
               (14, 13.4), (15.5, 12.9)]
        _poly(p, QPen, pts, '#2E7D32', 1.5)
        _line(p, QPen, (0.5, 15.2), (15.5, 15.2), DARK, 0.9)
    return _tool_icon(draw)
