# src/views/dialogs/data_analysis/peak_settings_help.py
"""The small window of the orange "?" in Detect Peaks (Peak Detection
Settings) and in the Peak list: what each setting means and its default.
"Full help…" opens the Peak Detection help page."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QPushButton, QTextBrowser, QVBoxLayout

from src.modules.data_analysis import peak_list as pl

LABEL_HELP = [
    ("Labels", "Which peaks get their number written. Once per band: one number per band, "
               "above its highest peak - the peaks of all spectra at about the same position are "
               "one band (as in the Peak list) and the number is the band's position, or its range "
               "(e.g. 247.2\u2013256.2) when the peaks move through the series; so many "
               "similar spectra do not cover the plot with the same numbers. On every peak: each "
               "peak its own number. Only the current spectrum: the peaks of the spectrum "
               "highlighted in the spectra list. None: no numbers. The red dots mark every peak "
               "in all cases.", "Once per band"),
    ("Font size", "The size of the numbers written next to the peaks.", "10"),
    ("Text rotation", "The angle of those numbers, in degrees (0 = horizontal).", "0"),
    ("Decimal places", "How many decimals the numbers have.", "2"),
    ("Number format", "Fixed point (1234.5), Scientific (1.2345e+03), General (the shorter of the "
                      "two) or Mixed (scientific only for very large or small numbers).",
     "Fixed Point"),
    ("Display format", "Write only the position (x) or the position and height (x, y).",
     "X value only"),
]


class PeakSettingsHelp(QDialog):
    """labels=True: also the settings of the numbers on the plot (Detect
    Peaks); columns=True: also what the columns of the Peak list mean."""

    def __init__(self, parent=None, labels=False, columns=False):
        super().__init__(parent)
        self.setWindowTitle("Peak settings – what each setting means")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.resize(780, 600 if (labels or columns) else 440)
        layout = QVBoxLayout(self)
        self.text = QTextBrowser()
        html = ('<p>The peaks are found in every spectrum on its own; the thresholds are fractions '
                'of that spectrum\'s own range, so the same settings suit spectra of very '
                'different sizes. The same text appears when you hold the mouse over a '
                'setting.</p>' + pl.settings_help_html(pl.SETTINGS_HELP))
        if labels:
            html += '<h4>The numbers on the plot</h4>' + pl.settings_help_html(LABEL_HELP)
        if columns:
            html += '<h4>The columns of the list</h4>' + pl.settings_help_html(pl.COLUMNS_HELP)
        self.text.setHtml(html)
        layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.more_button = QPushButton("Full help…")
        self.more_button.setToolTip("The Peak Detection help page")
        self.more_button.clicked.connect(self.full_help)
        buttons.addButton(self.more_button, QDialogButtonBox.HelpRole)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def full_help(self):
        from src.help.help_window import open_help_topic
        open_help_topic(self, 'peak_detection')


def tooltip_of(name):
    """The help text of one setting (for the tooltips)."""
    for n, what, default in pl.SETTINGS_HELP + LABEL_HELP:
        if n == name:
            return f"{what} Default: {default}."
    return ''
