# src/views/dialogs/visualization/publication_dialog.py
"""File › Save plot for publication…: the plot in the size of a journal
column (cm), one text size, lines at least so thick, at 300/600/1200 dpi
(TIFF, PNG) or as PDF / SVG / EPS - with a preview. The plot on the screen
is not changed (publication_figure works on a copy)."""

import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
                             QVBoxLayout)

from src.modules.visualization import publication_figure as pf

PREF_KEY = 'publication_figure'


class PublicationDialog(QDialog):
    def __init__(self, figure, parent=None, preferences=None, folder=''):
        super().__init__(parent)
        self.setWindowTitle("Save plot for publication")
        self.figure = figure
        self.preferences = preferences
        self.folder = folder
        self.saved_path = None
        s = dict(pf.DEFAULTS)
        try:
            s.update((preferences.get(PREF_KEY) or {}) if preferences is not None else {})
        except Exception:
            pass
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        form = QFormLayout()

        self.column_combo = QComboBox()
        for name, width in pf.COLUMNS:
            self.column_combo.addItem(f"{name} ({width:g} cm)", width)
        self.column_combo.addItem("own width", None)
        self.column_combo.setToolTip(
            "Width of a journal's column (most journals):\n"
            "1 column: 8.5 cm\n1.5 columns: 11.4 cm\n2 columns: 17.5 cm (the whole page)\n"
            "Own width: type it in Width.")
        form.addRow("Column:", self.column_combo)

        self.width_spin = self._spin(1.0, 50.0, s['width_cm'], " cm", 1)
        self.width_spin.setToolTip("Width: the width of the picture in the paper.")
        form.addRow("Width:", self.width_spin)
        self.height_spin = self._spin(1.0, 50.0, s['height_cm'], " cm", 1)
        self.height_spin.setToolTip("Height: the height of the picture in the paper.")
        form.addRow("Height:", self.height_spin)
        self.font_spin = self._spin(4.0, 24.0, s['font_pt'], " pt", 1)
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
        k = self.dpi_combo.findData(int(s['dpi']))
        self.dpi_combo.setCurrentIndex(k if k >= 0 else 1)
        self.dpi_combo.setToolTip(
            "Resolution of a TIFF or PNG picture (dots per inch):\n"
            "300 dpi: photographs, colour pictures\n"
            "600 dpi: line art, plots (most journals)\n"
            "1200 dpi: very fine lines\n"
            "PDF, SVG and EPS are sharp at any size (no dots).")
        form.addRow("Resolution:", self.dpi_combo)
        left.addLayout(form)
        self.pixels_label = QLabel()
        self.pixels_label.setStyleSheet("color: #555;")
        left.addWidget(self.pixels_label)
        left.addStretch(1)
        buttons = QHBoxLayout()
        from src.views import icons
        self.save_button = QPushButton("Save…")
        self.save_button.setIcon(icons.standard('SP_DialogSaveButton', self))
        self.save_button.setToolTip(
            "Save: choose the file and its kind (TIFF, PNG, PDF, SVG, EPS).")
        self.save_button.clicked.connect(self.save)
        close = QPushButton("Close")
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        help_button = icons.help_button("Saving a plot for a publication")
        help_button.clicked.connect(self._help)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close)
        buttons.addWidget(help_button)
        left.addLayout(buttons)
        layout.addLayout(left)

        right = QVBoxLayout()
        title = QLabel("Preview (the size in the paper, roughly):")
        right.addWidget(title)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setWidget(self.preview)
        scroll.setWidgetResizable(True)
        scroll.setMinimumSize(520, 380)
        right.addWidget(scroll, 1)
        layout.addLayout(right, 1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._update_preview)
        for w in (self.width_spin, self.height_spin, self.font_spin, self.line_spin):
            w.valueChanged.connect(lambda *_: self._changed())
        self.dpi_combo.currentIndexChanged.connect(lambda *_: self._changed())
        self.column_combo.currentIndexChanged.connect(lambda *_: self._column_chosen())
        self.width_spin.valueChanged.connect(lambda *_: self._match_column())
        self._match_column()
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

    # ------------------------------------------------------------------
    def settings(self):
        return {'width_cm': self.width_spin.value(), 'height_cm': self.height_spin.value(),
                'dpi': int(self.dpi_combo.currentData()), 'font_pt': self.font_spin.value(),
                'line_pt': self.line_spin.value()}

    def _column_chosen(self):
        width = self.column_combo.currentData()
        if width is not None:
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(width)
            self.width_spin.blockSignals(False)
            self._changed()

    def _match_column(self):
        w = self.width_spin.value()
        k = next((i for i in range(self.column_combo.count() - 1)
                  if abs(self.column_combo.itemData(i) - w) < 1e-6), self.column_combo.count() - 1)
        self.column_combo.blockSignals(True)
        self.column_combo.setCurrentIndex(k)
        self.column_combo.blockSignals(False)

    def _changed(self):
        s = self.settings()
        w, h = pf.pixels(s['width_cm'], s['height_cm'], s['dpi'])
        self.pixels_label.setText(f"TIFF / PNG: {w} × {h} pixels at {s['dpi']} dpi")
        self._timer.start()

    def _update_preview(self):
        s = self.settings()
        try:
            data = pf.preview_png(self.figure, s['width_cm'], s['height_cm'], s['font_pt'],
                                  s['line_pt'], dpi=self.logicalDpiX() or 96)
        except Exception:
            self.preview.setText("(no preview)")
            return
        pix = QPixmap()
        pix.loadFromData(data, 'PNG')
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
                                    s['font_pt'], s['line_pt'])
        except Exception as exc:
            QMessageBox.warning(self, "Save plot for publication",
                                f"The picture could not be saved:\n{exc}")
            return None
        if self.preferences is not None:
            try:
                self.preferences.set(PREF_KEY, s)
            except Exception:
                pass
        self.saved_path = path
        return path

    def _help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'publication')
