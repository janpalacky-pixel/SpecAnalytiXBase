# src/views/dialogs/visualization/publication_dialog.py
"""File › Save plot for publication…: the plot in the size of a journal
column, a page or a slide (cm), one text size, lines at least so thick, at
300/600/1200 dpi (TIFF, PNG) or as PDF / SVG / EPS - with a preview in which
the legend can be moved with the mouse; printing with a print preview. The
plot on the screen is not changed (publication_figure works on a copy)."""

import os

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QScrollArea, QVBoxLayout)

from src.modules.visualization import publication_figure as pf

PREF_KEY = 'publication_figure'


class PreviewLabel(QLabel):
    """The preview picture; a legend in it can be dragged with the mouse
    (`legend_moved(axes number, dx, dy)` in the picture's pixels)."""
    legend_moved = pyqtSignal(int, float, float)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setMouseTracking(True)
        self.boxes = []                 # [(axes number, legend box, frame)] in pixels
        self.ratio = 1.0                # picture pixels per screen pixel
        self._drag = None               # (axes number, QRectF, start point)
        self._shift = QPointF(0, 0)

    def _legend_at(self, pos):
        for i, box, frame in self.boxes:
            r = QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1])
            r = QRectF(r.x() / self.ratio, r.y() / self.ratio, r.width() / self.ratio,
                       r.height() / self.ratio)
            if r.contains(QPointF(pos)):
                return i, r
        return None

    def mousePressEvent(self, event):
        hit = self._legend_at(event.pos()) if event.button() == Qt.LeftButton else None
        if hit is None:
            return super().mousePressEvent(event)
        self._drag = (hit[0], hit[1], QPointF(event.pos()))
        self._shift = QPointF(0, 0)
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self._shift = QPointF(event.pos()) - self._drag[2]
            self.update()
            return
        self.setCursor(Qt.OpenHandCursor if self._legend_at(event.pos()) else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            return super().mouseReleaseEvent(event)
        i = self._drag[0]
        shift = QPointF(event.pos()) - self._drag[2]
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)
        self.update()
        if abs(shift.x()) + abs(shift.y()) >= 2:
            self.legend_moved.emit(i, shift.x() * self.ratio, shift.y() * self.ratio)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drag is not None:
            painter = QPainter(self)
            painter.setPen(QPen(Qt.darkBlue, 1, Qt.DashLine))
            painter.drawRect(self._drag[1].translated(self._shift))
            painter.end()


class PublicationDialog(QDialog):
    def __init__(self, figure, parent=None, preferences=None, folder=''):
        super().__init__(parent)
        self.setWindowTitle("Save plot for publication")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.figure = figure
        self.preferences = preferences
        self.folder = folder
        self.saved_path = None
        self.legend_xy = {}             # {axes number: (x, y)}: legends moved by the mouse
        self._quiet = False
        s = self._stored()
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        form = QFormLayout()

        self.column_combo = QComboBox()
        for name, width, height in pf.SIZES:
            size = f"{width:g} cm" if height is None else f"{width:g} × {height:g} cm"
            self.column_combo.addItem(f"{name} ({size})", (width, height))
        self.column_combo.addItem("own size", None)
        self.column_combo.setToolTip(
            "Size: of the picture.\n"
            "Columns of a journal (most journals; the height stays):\n"
            "1 column 8.5 cm, 1.5 columns 11.4 cm, 2 columns 17.5 cm.\n"
            "A page (inside margins of 1.5 cm) or a slide: width and height.\n"
            "For a page or a slide, a larger Text size (e.g. 12-16 pt) reads better.\n"
            "Own size: type it in Width and Height.")
        form.addRow("Size:", self.column_combo)

        self.width_spin = self._spin(1.0, 50.0, s['width_cm'], " cm", 1)
        self.width_spin.setToolTip("Width: the width of the picture in the paper.")
        form.addRow("Width:", self.width_spin)
        self.height_spin = self._spin(1.0, 50.0, s['height_cm'], " cm", 1)
        self.height_spin.setToolTip("Height: the height of the picture in the paper.")
        form.addRow("Height:", self.height_spin)
        self.font_spin = self._spin(4.0, 36.0, s['font_pt'], " pt", 1)
        self.font_spin.setToolTip(
            "Text size: of all labels, the numbers on the axes and the legend\n"
            "(titles 1 pt larger). Journals usually ask for 6-9 pt.")
        form.addRow("Text size:", self.font_spin)
        self.line_spin = self._spin(0.1, 5.0, s['line_pt'], " pt", 2)
        self.line_spin.setToolTip(
            "Lines at least: thinner lines are drawn this thick (thicker ones stay).\n"
            "Journals usually ask for at least 0.5-1 pt.")
        form.addRow("Lines at least:", self.line_spin)
        self.dpi_combo = QComboBox()
        for dpi in pf.DPI_CHOICES:
            self.dpi_combo.addItem(f"{dpi} dpi", dpi)
        self.dpi_combo.setToolTip(
            "Resolution of a TIFF or PNG picture (dots per inch):\n"
            "300 dpi: photographs, colour pictures\n"
            "600 dpi: line art, plots (most journals)\n"
            "1200 dpi: very fine lines\n"
            "PDF, SVG and EPS are sharp at any size (no dots).")
        form.addRow("Resolution:", self.dpi_combo)

        self.legend_combo = QComboBox()
        for key, text in pf.LEGENDS:
            self.legend_combo.addItem(text, key)
        self.legend_combo.setToolTip(
            "Legend: where it goes (its text 1 pt smaller than Text size).\n"
            "Best place: inside the plot, where it covers the fewest lines.\n"
            "Top right ... Bottom: that side or corner of the plot.\n"
            "No legend: without it.\n"
            "You can also drag the legend in the preview with the mouse.")
        self.place_combo = QComboBox()
        for key, text in pf.PLACES:
            self.place_combo.addItem(text, key)
        self.place_combo.setToolTip(
            "Inside the plot: over the plot's frame (the plot keeps its size).\n"
            "Outside the plot: beside, above or below it, not over the axes' numbers\n"
            "or titles; the picture keeps its size, so the plot in it gets smaller.\n"
            "Outside, the corners (e.g. Top right) are beside the plot, at its top or bottom.")
        row = QHBoxLayout()
        row.addWidget(self.legend_combo)
        row.addWidget(self.place_combo)
        form.addRow("Legend:", row)
        self.short_check = QCheckBox("Short names")
        self.short_check.setToolTip(
            "Short names: the spectra's names (legend, titles, a heatmap's rows)\n"
            "only with the part that tells them apart: \"raman_2comp_clean : raman_12\"\n"
            "-> \"raman_12\" (as \"shorten names\" in the main window).")
        form.addRow("", self.short_check)
        left.addLayout(form)
        self.pixels_label = QLabel()
        self.pixels_label.setStyleSheet("color: #555;")
        left.addWidget(self.pixels_label)

        printing = QGroupBox("Printing")
        pform = QFormLayout(printing)
        self.fit_combo = QComboBox()
        self.fit_combo.addItem("Fit to page", True)
        self.fit_combo.addItem("Actual size (Width × Height)", False)
        self.fit_combo.setToolTip(
            "On paper: how large the picture is printed.\n"
            "Fit to page: as large as the page lets it - the text grows with it\n"
            "(the page turns sideways for a wide picture).\n"
            "Actual size: in its size in cm, as it will be in the journal.")
        pform.addRow("On paper:", self.fit_combo)
        self.centre_combo = QComboBox()
        self.centre_combo.addItem("Centre of the page", True)
        self.centre_combo.addItem("Top left", False)
        self.centre_combo.setToolTip("Position: where on the page the picture is printed.")
        pform.addRow("Position:", self.centre_combo)
        self.grey_check = QCheckBox("Grey (black and white)")
        self.grey_check.setToolTip(
            "Grey: printed in shades of grey - to see whether the lines can be\n"
            "told apart in a black-and-white copy of the paper.")
        pform.addRow("", self.grey_check)
        self.caption_edit = QLineEdit()
        self.caption_edit.setPlaceholderText("(none)")
        self.caption_edit.setToolTip(
            "Caption: a line of text printed under the picture\n"
            "(e.g. the sample and the date). Not in the saved file.")
        pform.addRow("Caption:", self.caption_edit)
        left.addWidget(printing)
        left.addStretch(1)

        from src.views import icons
        self.save_button = QPushButton("Save…")
        self.save_button.setIcon(icons.standard('SP_DialogSaveButton', self))
        self.save_button.setToolTip(
            "Save: choose the file and its kind (TIFF, PNG, PDF, SVG, EPS).")
        self.save_button.setAutoDefault(False)            # Enter in a number box: not Save
        self.save_button.clicked.connect(lambda: self.save())
        self.preview_button = QPushButton("Print preview…")
        self.preview_button.setIcon(icons.standard('SP_FileDialogContentsView', self))
        self.preview_button.setAutoDefault(False)
        self.preview_button.setToolTip(
            "Print preview: the printed page, before printing - there the paper\n"
            "(A4, Letter ...), upright or sideways, and then Print.")
        self.preview_button.clicked.connect(lambda: self.print_preview())
        self.print_button = QPushButton("Print…")
        self.print_button.setIcon(icons.standard('SP_FileDialogDetailedView', self))
        self.print_button.setAutoDefault(False)
        self.print_button.setToolTip(
            "Print: choose the printer (or Microsoft Print to PDF) and print\n"
            "as set in Printing.")
        self.print_button.clicked.connect(lambda: self.print_figure())
        self.defaults_button = QPushButton("Restore defaults")
        self.defaults_button.setAutoDefault(False)
        self.defaults_button.setToolTip(
            "Restore defaults: all choices back as they were at first\n"
            "(1 column 8.5 × 6.5 cm, 8 pt, 1 pt, 600 dpi, legend at the best place).")
        self.defaults_button.clicked.connect(lambda: self.restore_defaults())
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        help_button = icons.help_button("Saving a plot for a publication")
        help_button.clicked.connect(self._help)
        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.print_button)
        left.addLayout(buttons)
        buttons2 = QHBoxLayout()
        buttons2.addWidget(self.defaults_button)
        buttons2.addStretch(1)
        buttons2.addWidget(close)
        buttons2.addWidget(help_button)
        left.addLayout(buttons2)
        layout.addLayout(left)

        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Preview:"))
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItem("Fit the window", True)
        self.zoom_combo.addItem("Real size (roughly)", False)
        self.zoom_combo.setToolTip(
            "Preview: Fit the window - the whole picture as large as the window lets it\n"
            "(the text grows with it, as on paper; larger when the window is maximized).\n"
            "Real size: about as large as on paper.")
        top.addWidget(self.zoom_combo)
        hint = QLabel("Drag the legend to move it.")
        hint.setStyleSheet("color: #555;")
        top.addWidget(hint)
        top.addStretch(1)
        right.addLayout(top)
        self.preview = PreviewLabel()
        self.preview.legend_moved.connect(self._legend_moved)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.preview)
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumSize(520, 380)
        right.addWidget(self.scroll, 1)
        layout.addLayout(right, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_preview)
        self._show(s)
        for w in (self.width_spin, self.height_spin, self.font_spin, self.line_spin):
            w.valueChanged.connect(lambda *_: self._changed())
        for w in (self.dpi_combo, self.fit_combo, self.centre_combo, self.zoom_combo):
            w.currentIndexChanged.connect(lambda *_: self._changed())
        self.legend_combo.currentIndexChanged.connect(lambda *_: self._legend_chosen())
        self.place_combo.currentIndexChanged.connect(lambda *_: self._legend_chosen())
        for w in (self.short_check, self.grey_check):
            w.toggled.connect(lambda *_: self._changed())
        self.column_combo.currentIndexChanged.connect(lambda *_: self._column_chosen())
        self.width_spin.valueChanged.connect(lambda *_: self._match_column())
        self.height_spin.valueChanged.connect(lambda *_: self._match_column())
        self._changed()

    @staticmethod
    def _spin(lo, hi, value, suffix, decimals):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        w.setSingleStep(0.5 if decimals == 1 else 0.25)
        w.setSuffix(suffix)
        w.setValue(float(value))
        return w

    def _stored(self):
        s = dict(pf.DEFAULTS)
        try:
            s.update((self.preferences.get(PREF_KEY) or {})
                     if self.preferences is not None else {})
        except Exception:
            pass
        s['legend'], s['legend_place'] = pf.legend_choice(s.get('legend'),
                                                          s.get('legend_place'))
        return s

    def _show(self, s):
        """Put the choices `s` into the window (without saving them again)."""
        self._quiet = True
        try:
            self.width_spin.setValue(float(s['width_cm']))
            self.height_spin.setValue(float(s['height_cm']))
            self.font_spin.setValue(float(s['font_pt']))
            self.line_spin.setValue(float(s['line_pt']))
            for combo, value, fallback in (
                    (self.dpi_combo, int(s['dpi']), 1),
                    (self.legend_combo, s['legend'], 0),
                    (self.place_combo, s['legend_place'], 0),
                    (self.fit_combo, bool(s['print_fit']), 0),
                    (self.centre_combo, bool(s['print_centre']), 0),
                    (self.zoom_combo, bool(s['preview_fit']), 0)):
                k = combo.findData(value)
                combo.setCurrentIndex(k if k >= 0 else fallback)
            self.short_check.setChecked(bool(s['short_names']))
            self.grey_check.setChecked(bool(s['print_grey']))
            self._place_enabled()
            self._match_column()
        finally:
            self._quiet = False

    # ------------------------------------------------------------------
    def settings(self):
        return {'width_cm': self.width_spin.value(), 'height_cm': self.height_spin.value(),
                'dpi': int(self.dpi_combo.currentData()), 'font_pt': self.font_spin.value(),
                'line_pt': self.line_spin.value(), 'legend': self.legend_combo.currentData(),
                'legend_place': self.place_combo.currentData(),
                'short_names': self.short_check.isChecked(),
                'print_fit': bool(self.fit_combo.currentData()),
                'print_centre': bool(self.centre_combo.currentData()),
                'print_grey': self.grey_check.isChecked(),
                'preview_fit': bool(self.zoom_combo.currentData())}

    def _choices(self):
        """The choices for publication_figure (with the moved legends)."""
        s = self.settings()
        return {'font_pt': s['font_pt'], 'line_pt': s['line_pt'], 'legend': s['legend'],
                'legend_place': s['legend_place'], 'short_names': s['short_names'],
                'legend_xy': dict(self.legend_xy)}

    def _remember(self):
        """The choices are kept for the next time (also without saving)."""
        if self.preferences is not None and not self._quiet:
            try:
                self.preferences.set(PREF_KEY, self.settings())
            except Exception:
                pass

    def restore_defaults(self):
        self.legend_xy = {}
        self._show(dict(pf.DEFAULTS))
        self._changed()

    def _render(self, dpi):
        s = self.settings()
        return pf.render(self.figure, s['width_cm'], s['height_cm'], dpi, **self._choices())

    def _picture(self, dpi):
        return self._render(dpi)[0]

    def _column_chosen(self):
        size = self.column_combo.currentData()
        if size is None:
            return
        width, height = size
        for spin, value in ((self.width_spin, width), (self.height_spin, height)):
            if value is not None:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self._changed()

    def _match_column(self):
        w, h = self.width_spin.value(), self.height_spin.value()
        last = self.column_combo.count() - 1
        k = last
        for i in range(last):
            width, height = self.column_combo.itemData(i)
            if abs(width - w) < 1e-6 and (height is None or abs(height - h) < 1e-6):
                k = i
                if height is not None:
                    break                       # a page / slide fits better than a column
        self.column_combo.blockSignals(True)
        self.column_combo.setCurrentIndex(k)
        self.column_combo.blockSignals(False)

    def _place_enabled(self):
        self.place_combo.setEnabled(self.legend_combo.currentData() not in ('best', 'none'))

    def _legend_chosen(self):
        self._place_enabled()
        self.legend_xy = {}                     # a chosen place: the moved legend goes there
        self._changed()

    def _legend_moved(self, i, dx, dy):
        for k, box, frame in self.preview.boxes:
            if k == i:
                self.legend_xy[i] = pf.moved_legend(box, frame, dx, dy)
                self._update_preview()
                return

    def _changed(self):
        if self._quiet:
            return
        s = self.settings()
        w, h = pf.pixels(s['width_cm'], s['height_cm'], s['dpi'])
        self.pixels_label.setText(f"TIFF / PNG: {w} × {h} pixels at {s['dpi']} dpi")
        self._remember()
        self._timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom_combo.currentData():
            self._timer.start()

    def _preview_dpi(self):
        s = self.settings()
        real = self.logicalDpiX() or 96
        if not s['preview_fit']:
            return real
        view = self.scroll.viewport().size()
        w_in, h_in = s['width_cm'] / 2.54, s['height_cm'] / 2.54
        return max(20.0, min((view.width() - 4) / w_in, (view.height() - 4) / h_in))

    def _update_preview(self):
        ratio = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0
        try:
            data, boxes = self._render(self._preview_dpi() * ratio)
        except Exception:
            self.preview.boxes = []
            self.preview.setText("(no preview)")
            return
        pix = QPixmap()
        pix.loadFromData(data, 'PNG')
        pix.setDevicePixelRatio(ratio)
        self.preview.ratio = ratio
        self.preview.boxes = boxes
        self.preview.setPixmap(pix)

    def save(self, path=None):
        """Ask for the file (or `path`) and save; returns the path or None."""
        s = self.settings()
        if path is None:
            filters = ";;".join(f"{name} (*.{ext})" for name, ext in pf.FORMATS)
            start = os.path.join(self.folder or '', 'figure.tif')
            path, chosen = QFileDialog.getSaveFileName(self, "Save plot for publication",
                                                       start, filters)
            if not path:
                return None
            ext = next((e for n, e in pf.FORMATS if chosen.startswith(n)), 'tif')
            if '.' not in os.path.basename(path):
                path += '.' + ext
        try:
            pf.save_for_publication(self.figure, path, s['width_cm'], s['height_cm'], s['dpi'],
                                    **self._choices())
        except Exception as exc:
            QMessageBox.warning(self, "Save plot for publication",
                                f"The picture could not be saved:\n{exc}")
            return None
        self._remember()
        self.saved_path = path
        return path

    # ------------------------------------------------------------------ printing
    def _new_printer(self):
        from PyQt5.QtGui import QPageLayout
        from PyQt5.QtPrintSupport import QPrinter
        printer = QPrinter(QPrinter.HighResolution)
        s = self.settings()
        wide = s['width_cm'] > s['height_cm'] if s['print_fit'] else s['width_cm'] > 19.0
        printer.setPageOrientation(QPageLayout.Landscape if wide else QPageLayout.Portrait)
        return printer

    def paint_page(self, printer):
        """Draw the picture (and the caption) on the printer's page."""
        from PyQt5.QtGui import QFont, QImage
        from PyQt5.QtPrintSupport import QPrinter
        s = self.settings()
        res = printer.resolution() or 600
        page = printer.pageRect(QPrinter.DevicePixel)
        caption = self.caption_edit.text().strip()
        caption_h = res * 0.4 if caption else 0.0
        pic_w, pic_h = s['width_cm'] / 2.54 * res, s['height_cm'] / 2.54 * res
        x, y, w, h = pf.print_place(page.width(), page.height(), pic_w, pic_h,
                                    s['print_fit'], s['print_centre'], caption_h)
        scale = w / pic_w
        dpi = min(600.0, float(res)) * scale             # sharp, not too many pixels
        dpi = min(dpi, 9000 / max(s['width_cm'], s['height_cm']) * 2.54)
        image = QImage.fromData(self._picture(max(72.0, dpi)), 'PNG')
        if s['print_grey']:
            image = image.convertToFormat(QImage.Format_Grayscale8)
        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "Print", "The printer could not be started.")
            return False
        try:
            painter.drawImage(QRectF(x, y, w, h), image)
            if caption:
                font = QFont(self.font())
                font.setPointSizeF(12)
                painter.setFont(font)
                painter.drawText(QRectF(x, y + h + res * 0.08, max(w, res * 3), caption_h),
                                 Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, caption)
        finally:
            painter.end()
        return True

    def print_figure(self, printer=None):
        """Print as set in Printing; without `printer` the printer is asked
        for first."""
        from PyQt5.QtPrintSupport import QPrintDialog
        if printer is None:
            printer = self._new_printer()
            if QPrintDialog(printer, self).exec_() != QDialog.Accepted:
                return False
        ok = self.paint_page(printer)
        self._remember()
        return ok

    def print_preview(self, run=True):
        """The print preview (paper, upright / sideways, Print). Returns the
        preview window."""
        from PyQt5.QtPrintSupport import QPrintPreviewDialog
        # the printer must live as long as the preview (Qt does not keep it:
        # a temporary one was deleted by Python at once - a crash)
        self._preview_printer = self._new_printer()
        dlg = QPrintPreviewDialog(self._preview_printer, self)
        dlg.setWindowTitle("Print preview")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowMinMaxButtonsHint)
        dlg.paintRequested.connect(self.paint_page)
        dlg.resize(900, 700)
        if run:
            dlg.exec_()
        return dlg

    def _help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'publication')
