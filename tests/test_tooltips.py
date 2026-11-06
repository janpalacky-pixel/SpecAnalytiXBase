"""Every window shows its tooltips with the names of its options in bold
(as Peak Fitting): a term before a colon, and the name of a tick box or a
round choice button first in its tooltip."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPoint
from PyQt5.QtGui import QHelpEvent
from PyQt5.QtWidgets import (QApplication, QCheckBox, QDialog, QPushButton, QRadioButton,
                             QToolTip, QVBoxLayout)

from src.views import tooltips

app = QApplication.instance() or QApplication([])


def _shown(widget):
    app.sendEvent(widget, QHelpEvent(QEvent.ToolTip, QPoint(3, 3), widget.mapToGlobal(QPoint(3, 3))))
    return QToolTip.text()


def test_the_name_of_a_tick_box_comes_first():
    box, radio, button = QCheckBox('Show &legend'), QRadioButton('Peak intensity    I / Imax'), \
        QPushButton('Run')
    assert tooltips.named(box, 'Show the legend in the plot') == \
        'Show legend: Show the legend in the plot'
    assert tooltips.named(radio, 'Divides by the maximum.') == 'Peak intensity: Divides by the maximum.'
    assert tooltips.named(box, 'Show legend: as it says') == 'Show legend: as it says'   # already
    assert tooltips.named(box, 'Unchecked (default): a\nChecked: b').startswith('Unchecked')
    assert tooltips.named(button, 'Runs it') == 'Runs it'               # not a choice
    assert tooltips.named(QCheckBox('Custom target:'), 'Multiply it') == 'Custom target: Multiply it'
    assert tooltips.named(box, 'PCA of the data') == 'Show legend: PCA of the data'  # PCA kept


def test_every_window_shows_bold_names():
    tooltips.install(app)
    dlg = QDialog()
    layout = QVBoxLayout(dlg)
    box = QCheckBox('Show legend')
    box.setToolTip('Show the legend in the plot')
    combo_like = QPushButton('Method')
    combo_like.setToolTip('How:\nArea: the area\nMax: the maximum')
    layout.addWidget(box)
    layout.addWidget(combo_like)
    dlg.show()
    try:
        app.processEvents()
        assert '<b>Show legend</b>: Show the legend' in _shown(box)
        text = _shown(combo_like)
        assert '<b>Area</b>: the area' in text and '<b>Max</b>: the maximum' in text
        dlg.setProperty(tooltips.RICH, False)                   # switched off: plain
        assert '<b>' not in _shown(box)
    finally:
        QToolTip.hideText()
        dlg.hide()
        tooltips.uninstall()


def test_the_question_mark_of_tabs_sits_right_after_the_last_tab():
    from PyQt5.QtWidgets import QTabWidget, QWidget
    from src.views import icons
    tabs = QTabWidget()
    tabs.addTab(QWidget(), 'Intensity')
    tabs.addTab(QWidget(), 'Scatter correction')
    tabs.resize(600, 300)
    b = icons.place_after_tabs(tabs, icons.help_button('Method info: what it does'))
    tabs.show()
    for _ in range(5):
        app.processEvents()
    bar = tabs.tabBar()
    right = bar.mapTo(tabs, bar.tabRect(1).topRight()).x()
    assert b.parent() is tabs and b.isVisible() and right < b.x() < right + 20
    tabs.hide()


def test_the_real_normalization_window():
    """Scatter correction: the round buttons begin with their names in bold
    (an abbreviation with a dot is a term), the words after them as written;
    the MSC tick box: its lines Unchecked (default) / Checked in bold."""
    from src.views.dialogs.data_analysis.normalization_dialog import NormalizationDialog
    tooltips.install(app)
    dlg = NormalizationDialog()
    dlg.show()
    try:
        app.processEvents()
        snv = next(r for r in dlg._radio_map.values() if r.text().startswith('Scatter corr. (SNV)'))
        dlg.method_tabs.setCurrentIndex(1)
        app.processEvents()
        text = _shown(snv)
        assert '<b>Scatter corr. (SNV)</b>: Standard Normal Variate' in text, text
        dlg.msc_use_region_cb.setVisible(True)
        app.processEvents()
        text = _shown(dlg.msc_use_region_cb)
        assert '<b>Unchecked (default)</b>:' in text and '<b>Checked</b>:' in text, text
    finally:
        QToolTip.hideText()
        dlg.hide()
        tooltips.uninstall()
