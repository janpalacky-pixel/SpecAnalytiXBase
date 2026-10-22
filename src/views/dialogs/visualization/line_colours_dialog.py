# src/views/dialogs/visualization/line_colours_dialog.py
"""Line colours (the "…" next to the line colours list, View menu, right-click
on the plot or on the spectra list): one place for the three ways the lines
get their colour - automatic, own colours (Plot Properties) or by value
(a colour scale, ColorByValuePanel). The controller is
src/controllers/visualization/line_colours_controller.py."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
                             QLabel, QPushButton, QRadioButton, QVBoxLayout)

from src.views import icons
from src.views.dialogs.visualization.color_by_value_dialog import ColorByValuePanel

MODES = ('automatic', 'own', 'value')
CHOICE_TEXT = {
    'automatic': "Automatic colours",
    'own': "Own colours",
    'value': "Colours by value",
}
CHOICE_HINT = {
    'automatic': "The standard sequence of colours (blue, orange, green, …). "
                 "Line style and width from Plot Properties are still used.",
    'own': "Every spectrum is drawn in the colour set for it in Plot Properties "
           "(blue when none is set).",
    'value': "The lines of the Overlay, Waterfall and Grid plots get their colour from a colour "
             "scale, with a colour bar next to the plot. Spectra without a value are drawn grey.",
}


class LineColoursDialog(QDialog):
    """apply_callback(mode, by_value_settings); set_own_colours() opens
    the Plot Properties window for the selected spectra."""

    def __init__(self, parent, spectra, mode, by_value_settings=None,
                 apply_callback=None, set_own_colours=None):
        super().__init__(parent)
        self.setWindowTitle("Line colours")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(600, 840)
        self.apply_callback = apply_callback
        self.set_own_colours = set_own_colours
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        intro = QLabel("How the lines of the plot get their colour:")
        top.addWidget(intro, 1)
        help_btn = icons.help_button("Line colours in the User Guide")
        help_btn.clicked.connect(self.show_help)
        top.addWidget(help_btn, 0, Qt.AlignTop)
        layout.addLayout(top)

        self.group = QButtonGroup(self)
        self.radios = {}
        for m in MODES:
            box = QGroupBox()
            box_layout = QVBoxLayout(box)
            radio = QRadioButton(CHOICE_TEXT[m])
            font = radio.font()
            font.setBold(True)
            radio.setFont(font)
            self.radios[m] = radio
            self.group.addButton(radio)
            box_layout.addWidget(radio)
            hint = QLabel(CHOICE_HINT[m])
            hint.setWordWrap(True)
            hint.setContentsMargins(22, 0, 0, 0)
            box_layout.addWidget(hint)
            if m == 'own':
                self.own_button = QPushButton("Set the colour of the selected spectra…")
                self.own_button.setToolTip("Plot Properties (colour, line style, "
                                           "width, markers)")
                self.own_button.clicked.connect(self._own)
                row = QHBoxLayout()
                row.setContentsMargins(22, 0, 0, 0)
                row.addWidget(self.own_button)
                row.addStretch(1)
                box_layout.addLayout(row)
            if m == 'value':
                self.panel = ColorByValuePanel(spectra, by_value_settings, include_off=False)
                self.panel.setContentsMargins(22, 0, 0, 0)
                self.panel.preview.setMinimumHeight(150)
                box_layout.addWidget(self.panel, 1)
            layout.addWidget(box, 1 if m == 'value' else 0)

        self.radios[mode if mode in MODES else 'automatic'].setChecked(True)
        for radio in self.radios.values():
            radio.toggled.connect(self._enable)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        layout.addWidget(buttons)
        self.buttons = buttons
        self._enable()

    def mode(self):
        return next(m for m, r in self.radios.items() if r.isChecked())

    def _enable(self, *_):
        self.panel.setEnabled(self.mode() == 'value')
        self.own_button.setEnabled(self.mode() == 'own')

    def _own(self):
        if self.set_own_colours is not None:
            self.set_own_colours()

    def apply(self):
        if self.apply_callback is not None:
            self.apply_callback(self.mode(), self.panel.settings())

    def _ok(self):
        self.apply()
        self.accept()

    def show_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'user_guide', 'line-colours')
