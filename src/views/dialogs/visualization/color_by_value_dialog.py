# src/views/dialogs/visualization/color_by_value_dialog.py
"""The "Colours by value" settings: what the colour comes from, the colour
scale, and a preview of the values of the selected spectra
(src/modules/visualization/color_by_value.py). ColorByValuePanel is part of
the Line colours window (line_colours_dialog.py); ColorByValueDialog shows
the panel on its own."""

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QImage, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from src.modules.visualization import color_by_value as cbv

_PREVIEW_ROWS = 12


def _gradient_icon(name, width=64, height=12):
    import matplotlib
    cmap = matplotlib.colormaps[name]
    rgba = (cmap(np.linspace(0, 1, width))[:, :3] * 255).astype(np.uint8)
    data = np.ascontiguousarray(np.repeat(rgba[None, :, :], height, axis=0))
    image = QImage(data.data, width, height, 3 * width, QImage.Format_RGB888).copy()
    return QIcon(QPixmap.fromImage(image))


class ColorByValuePanel(QWidget):
    """include_off=False (the Line colours window): no "Off" choice - the
    usual colours are the window's other choices; an "off" setting is shown
    as 'Order in the spectra list'."""

    def __init__(self, spectra, settings=None, include_off=True, parent=None):
        super().__init__(parent)
        self.spectra = list(spectra)
        s = cbv.normalized(settings)
        modes = [m for m in cbv.MODES if include_off or m != 'off']
        if s['mode'] not in modes:
            s['mode'] = 'order'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.mode_combo = QComboBox()
        for mode in modes:
            self.mode_combo.addItem(cbv.MODE_TEXT[mode], mode)
        self.mode_combo.setCurrentIndex(modes.index(s['mode']))
        form.addRow("Colour by:", self.mode_combo)

        self.number_combo = QComboBox()
        for index, text in cbv.name_number_choices(self.spectra):
            self.number_combo.addItem(text, index)
        i = self.number_combo.findData(s['number'])
        self.number_combo.setCurrentIndex(max(i, 0))
        self.number_combo.setToolTip("Which number of the name, e.g. in 'TBA_45C : 0003' the first "
                                     "is 45 and the last is 3")
        form.addRow("Use:", self.number_combo)

        self.key_combo = QComboBox()
        for key in cbv.metadata_keys(self.spectra):
            self.key_combo.addItem(key)
        if s['metadata_key']:
            j = self.key_combo.findText(s['metadata_key'])
            if j >= 0:
                self.key_combo.setCurrentIndex(j)
        form.addRow("Value:", self.key_combo)

        self.cmap_combo = QComboBox()
        for name in cbv.COLORMAPS:
            self.cmap_combo.addItem(_gradient_icon(name), name)
        self.cmap_combo.setCurrentText(s['colormap'])
        form.addRow("Colour scale:", self.cmap_combo)
        self.reverse_check = QCheckBox("Reverse the colour scale")
        self.reverse_check.setChecked(s['reverse'])
        form.addRow("", self.reverse_check)
        self.colorbar_check = QCheckBox("Show the colour bar")
        self.colorbar_check.setChecked(s['colorbar'])
        form.addRow("", self.colorbar_check)
        layout.addLayout(form)

        self.preview = QTableWidget(0, 2)
        self.preview.setHorizontalHeaderLabels(["Spectrum", "Value"])
        self.preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.preview.verticalHeader().setVisible(False)
        self.preview.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.preview, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        for w in (self.mode_combo, self.number_combo, self.key_combo, self.cmap_combo):
            w.currentIndexChanged.connect(self.refresh)
        self.reverse_check.toggled.connect(self.refresh)
        self.refresh()

    def settings(self):
        return cbv.normalized({
            'mode': self.mode_combo.currentData(),
            'number': self.number_combo.currentData(),
            'metadata_key': self.key_combo.currentText(),
            'colormap': self.cmap_combo.currentText(),
            'reverse': self.reverse_check.isChecked(),
            'colorbar': self.colorbar_check.isChecked(),
        })

    def refresh(self, *_):
        s = self.settings()
        mode = s['mode']
        self.number_combo.setEnabled(mode == 'name')
        self.key_combo.setEnabled(mode == 'metadata' and self.key_combo.count() > 0)
        for w in (self.cmap_combo, self.reverse_check, self.colorbar_check):
            w.setEnabled(mode != 'off')
        self.preview.setRowCount(0)
        if mode == 'off':
            self.summary.setText("The plots use their usual colours.")
            return
        if mode == 'metadata' and self.key_combo.count() == 0:
            self.summary.setText("The selected spectra have no stored numbers (metadata) to colour "
                                 "by. Try a number in the name.")
            return
        vals = cbv.values(self.spectra, s)
        cols = cbv.colours(vals, s)
        shown = list(range(min(len(self.spectra), _PREVIEW_ROWS)))
        self.preview.setRowCount(len(shown))
        for r in shown:
            name = QTableWidgetItem(str(self.spectra[r].get('label', '')))
            name.setIcon(self._swatch(cols[r]))
            value = QTableWidgetItem('—' if vals[r] is None else f'{vals[r]:g}')
            value.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
            self.preview.setItem(r, 0, name)
            self.preview.setItem(r, 1, value)
        known = [v for v in vals if v is not None]
        missing = len(vals) - len(known)
        text = (f"{len(known)} of {len(vals)} spectra have a value"
                + (f" (from {min(known):g} to {max(known):g})" if known else "")
                + (f"; {missing} without a value are drawn grey." if missing else "."))
        if len(self.spectra) > _PREVIEW_ROWS:
            text += f" The list shows the first {_PREVIEW_ROWS}."
        self.summary.setText(text)

    @staticmethod
    def _swatch(colour):
        pix = QPixmap(14, 14)
        pix.fill(QColor(colour))
        return QIcon(pix)



class ColorByValueDialog(QDialog):
    """The panel on its own, with OK / Apply / Cancel."""

    def __init__(self, parent, spectra, settings=None, apply_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Colours by value")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(560, 560)
        self.apply_callback = apply_callback
        layout = QVBoxLayout(self)
        intro = QLabel(
            "The lines of the Overlay, Waterfall and Grid plots get their colour from a colour "
            "scale, with a colour bar next to the plot. Spectra without a value are drawn grey.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.panel = ColorByValuePanel(spectra, settings, include_off=True)
        layout.addWidget(self.panel, 1)
        for name in ('spectra', 'mode_combo', 'number_combo', 'key_combo', 'cmap_combo',
                     'reverse_check', 'colorbar_check', 'preview', 'summary'):
            setattr(self, name, getattr(self.panel, name))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self.buttons = buttons

    def settings(self):
        return self.panel.settings()

    def apply(self):
        if self.apply_callback is not None:
            self.apply_callback(self.settings())

    def _ok(self):
        self.apply()
        self.accept()
