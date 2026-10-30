"""The buttons of the most used tools under the menu bar, in groups (Main,
Spectra processing, Analysis & visualization, Help), do what their menu
entries do; the groups can be hidden and the text left out (View >
Toolbars, remembered); every entry of the menus Spectra processing and
Analysis & Visualization has an icon. Peak list is also in the menu
Analysis & Visualization > Data Analysis, the Data table also in the plot's
right-click menu."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QToolButton

app = QApplication.instance() or QApplication([])


@pytest.fixture
def mc(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _button(v, name):
    return v.findChild(QToolButton, name)


def test_each_tool_button_triggers_its_menu_action(mc):
    v = mc.view
    pairs = [('toolbarDataRangeButton', v.actionMenuOpsDataRange),
             ('toolbarSmoothingButton', v.actionMenuOpsSGSmoothing),
             ('toolbarBaselineButton', v.actionMenuOpsAutomatedBaseline),
             ('toolbarNormalizationButton', v.actionMenuOpsNormalization),
             ('toolbarPeakListButton', v.actionMenuPeakList),
             ('toolbarPeakFittingButton', v.actionMenuPeakFitting),
             ('toolbarSVDAnalysisButton', v.actionMenuSVDAnalysis),
             ('toolbar2DMapButton', v.actionMenu2DMap),
             ('toolbarGroupStatisticsButton', v.actionMenuGroupStatistics),
             ('toolbarDataTableButton', v.actionMenuDataTable),
             ('toolbarCopyPlotButton', v.actionCopyPlot)]
    for name, action in pairs:
        b = _button(v, name)
        assert b is not None, name
        assert b.defaultAction() is action
        assert not action.icon().isNull() and action.toolTip()


def test_peak_list_in_the_menu_and_opens_the_peaks_window(mc, monkeypatch):
    v = mc.view
    texts = [a.text() for a in v.menuAnalysisVisualizationData.actions()]
    assert texts.index('Peak list…') + 1 == texts.index('Peak Fitting')
    called = []
    monkeypatch.setattr(mc.peak_detection_controller, 'show_peak_list',
                        lambda *a, **k: called.append(1))
    v.actionMenuPeakList.trigger()
    assert called == [1]


def test_data_table_in_the_plot_menu_under_peak_list(mc, monkeypatch):
    from PyQt5.QtWidgets import QMenu
    seen = []

    def fake_exec(menu, *a, **k):
        seen.extend(a.text() for a in menu.actions())
        return next(a for a in menu.actions() if a.text() == 'Data table…')
    monkeypatch.setattr(QMenu, 'exec_', fake_exec)
    opened = []
    mc.view.actionMenuDataTable.triggered.connect(lambda *a: opened.append(1))
    monkeypatch.setattr(mc, 'run_visualization_analysis', lambda *a, **k: None)

    from PyQt5.QtWidgets import QWidget
    if getattr(mc, 'static_canvas', None) is None:
        monkeypatch.setattr(mc, 'static_canvas', QWidget(), raising=False)

    class E:
        x, y, button = 10, 10, 3
    mc.show_context_menu(E())
    assert seen.index('Data table…') == seen.index('Peak list…') + 1
    assert opened == [1]


def test_every_entry_of_the_two_menus_has_an_icon(mc):
    v = mc.view

    def walk(menu):
        for a in menu.actions():
            if a.isSeparator():
                continue
            yield a
            if a.menu() is not None:
                yield from walk(a.menu())
    for menu in (v.menuSpectraProcessingOps, v.menuAnalysisVisualization):
        missing = [a.text() for a in walk(menu) if a.icon().isNull()]
        assert missing == [], missing


def test_groups_can_be_hidden_and_the_text_left_out(mc, tmp_path):
    from PyQt5.QtCore import Qt
    from src.views import toolbars
    v = mc.view
    v.resize(2600, 900)
    v.show()
    app.processEvents()
    texts = [a.text() for a in v.menuToolbars.actions() if not a.isSeparator()]
    assert texts == ['Main buttons (Import, Open snapshot, Save, Help, Copy plot)',
                     'Spectra processing', 'Analysis && visualization', 'Text on the buttons',
                     'Back to the default (all groups, text: Automatic)']
    assert [a.text() for a in v.menuToolbarText.actions()] == \
        ['Automatic (when there is room)', 'Always', 'Never - only the icons']
    popup = v.createPopupMenu()                                  # right-click on the buttons
    assert [a.text() for a in popup.actions() if not a.isSeparator()] == texts
    v.processingToolBar.toggleViewAction().trigger()             # hide a group
    assert not v.processingToolBar.isVisible()
    assert toolbars.saved()['processing'] is False               # remembered
    v.toolbarTextActions['never'].trigger()                      # icons only
    assert v.analysisToolBar.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert v.toolbarImportButton.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert toolbars.saved()['text'] == 'never'
    again = type(mc)()                                           # the next start
    try:
        assert again.view.processingToolBar.isHidden()
        assert again.view.analysisToolBar.toolButtonStyle() == Qt.ToolButtonIconOnly
        assert again.view.toolbarTextActions['never'].isChecked()
    finally:
        again.autosave_controller.shutdown()
        again.view.deleteLater()
    v.processingToolBar.toggleViewAction().trigger()
    v.toolbarTextActions['auto'].trigger()
    assert v.processingToolBar.isVisible() and toolbars.saved() == {
        'main': True, 'processing': True, 'analysis': True, 'text': 'auto'}


def test_automatic_text_leaves_it_out_group_by_group_when_narrow(mc):
    """No button behind the "»": in a narrow window Analysis shows only icons
    first, then Processing, ... - also when the measured widths were wrong."""
    from PyQt5.QtCore import Qt
    v = mc.view
    v.show()
    styles = {}
    for width in (2600, 1150, 700):
        v.resize(width, 800)
        app.processEvents()
        styles[width] = [tb.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
                         for tb in (v.mainToolBar, v.processingToolBar, v.analysisToolBar)]
    assert styles[2600] == [True, True, True]                     # room for all the text
    assert styles[1150][2] is False                              # Analysis first
    assert styles[700] == [False, False, False] or styles[700][:2] != [True, True]
    v.resize(2600, 800)
    from PyQt5.QtTest import QTest
    QTest.qWait(400)
    assert all(tb.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
               for tb in (v.mainToolBar, v.processingToolBar, v.analysisToolBar))


def test_a_group_that_still_overflows_loses_its_text(mc):
    """Wrong measured widths (e.g. measured before the window was drawn):
    the check after the layout still takes the text away."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    v = mc.view
    v.show()
    v.resize(1200, 800)
    app.processEvents()
    v._toolbar_widths = {k: 10 for k in v._toolbar_widths}       # far too small
    v.resize(1210, 800)
    QTest.qWait(600)
    bars = (v.mainToolBar, v.processingToolBar, v.analysisToolBar)
    assert all(tb.width() + 2 >= tb.sizeHint().width() for tb in bars)   # nothing behind »
    assert v.analysisToolBar.toolButtonStyle() == Qt.ToolButtonIconOnly


def test_help_comes_right_after_save(mc):
    tb = mc.view.mainToolBar
    names = [tb.widgetForAction(a).objectName() for a in tb.actions()
             if not a.isSeparator() and tb.widgetForAction(a) is not None]
    assert names[:5] == ['toolbarImportButton', 'toolbarOpensnapshotButton', 'toolbarSaveButton',
                         'toolbarHelpButton', 'toolbarCopyPlotButton']


def test_back_to_the_default(mc):
    from src.modules.misc.session_files import Preferences
    from src.views import toolbars
    v = mc.view
    v.show()
    v.analysisToolBar.toggleViewAction().trigger()
    v.toolbarTextActions['never'].trigger()
    assert Preferences().get('toolbars') is not None
    v.actionToolbarsDefault.trigger()
    assert all(tb.isVisible() for tb in toolbars.tool_bars(v).values())
    assert v.toolbarTextActions['auto'].isChecked() and v.toolbarTextMode == 'auto'
    assert Preferences().get('toolbars') is None                 # nothing stored any more


def test_every_entry_of_the_help_menu_has_an_icon(mc):
    from src.views import toolbars
    v = mc.view
    toolbars.apply_help_icons(v)                                 # (also when it opens)

    def walk(menu):
        for a in menu.actions():
            if not a.isSeparator():
                yield a
                if a.menu() is not None:
                    yield from walk(a.menu())
    datasets = next(a.menu() for a in v.menuHelp.actions() if a.text() == 'Test datasets')
    inside = set(walk(datasets))
    missing = [a.text() for a in walk(v.menuHelp) if a.icon().isNull() and a not in inside]
    assert missing == [], missing
    # Test datasets: its own icon, Synthetic and Real (measured) each another one; the
    # datasets and their groups none (only the folder and download entries)
    tops = {a.text(): a for a in datasets.actions() if not a.isSeparator()}
    synth, real = tops['Synthetic'], tops['Real (measured)']
    assert not synth.icon().isNull() and not real.icon().isNull()
    assert synth.icon().cacheKey() != real.icon().cacheKey()
    with_icon = [a.text() for a in inside if not a.icon().isNull()]
    assert sorted(with_icon) == sorted(['Synthetic', 'Real (measured)']
                                       + [a.text() for a in inside if a.objectName() in (
                                           'actionOpenSyntheticFolder', 'actionOpenRealFolder',
                                           'actionDownloadLargeDatasets')])
    # the help of a tool has the icon of that tool
    assert v.actionNormalizationHelp.icon().cacheKey() == \
        v.actionMenuOpsNormalization.icon().cacheKey()
