# src/controllers/visualization/plot_clipboard.py
"""Copy the plot to the clipboard (Ctrl+Shift+C, File menu, right-click on
the plot): the figure as a picture, to paste straight into Word, PowerPoint
or an e-mail - at print resolution, in the size it has on the screen."""

import io

COPY_DPI = 300                     # dots per inch of the copied picture


def figure_image(figure, dpi=COPY_DPI):
    """The figure as a QImage of *dpi* dots per inch, on a white background.
    The resolution is stored in the picture, so Word / PowerPoint paste it in
    the size it has on the screen (not 3x larger)."""
    from PyQt5.QtGui import QImage
    buf = io.BytesIO()
    figure.savefig(buf, format='png', dpi=dpi, facecolor='white')
    image = QImage.fromData(buf.getvalue(), 'PNG')
    dots_per_metre = int(round(dpi / 0.0254))
    image.setDotsPerMeterX(dots_per_metre)
    image.setDotsPerMeterY(dots_per_metre)
    return image


def copy_figure(figure, dpi=COPY_DPI):
    """Put the figure on the clipboard; returns the QImage (or None)."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
    QApplication.setOverrideCursor(Qt.WaitCursor)       # many spectra take a moment
    try:
        image = figure_image(figure, dpi)
    finally:
        QApplication.restoreOverrideCursor()
    if image.isNull():
        return None
    QApplication.clipboard().setImage(image)
    return image
