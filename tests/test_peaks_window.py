"""The Peaks window: Detect Peaks and the Peak list in one window - one set of
settings at the top for the tabs List, Plot, Band table and Mark on the plot
(the red dots and numbers on the main plot, which follow the settings once
marked)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


def _spectra(n=3):
    x = np.linspace(0, 100, 501)
    return [{'label': f's{k}', 'x_scale': x,
             'y_scale': np.exp(-((x - 30) / 3) ** 2) + 0.5 * np.exp(-((x - 70) / 3) ** 2)}
            for k in range(n)]


class _Plot:
    """Stands for the controller: what was marked / removed."""
    def __init__(self):
        self.marked, self.removed = [], 0

    def mark(self, settings):
        self.marked.append(dict(settings))

    def clear(self):
        self.removed += 1


def _window(start_tab='list', **kw):
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    plot = _Plot()
    dlg = PeakListDialog(None, _spectra(), mark=plot.mark, clear_marks=plot.clear,
                         start_tab=start_tab, **kw)
    return dlg, plot


def test_one_window_with_four_tabs():
    dlg, _ = _window()
    assert dlg.windowTitle() == 'Peaks – 3 spectra'
    assert [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())] == \
        ['List', 'Plot', 'Band table', 'Mark on the plot']
    assert dlg.tabs.currentIndex() == 0 and dlg.table.rowCount() == 6


def test_without_the_main_plot_there_is_no_tab_mark():
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog
    dlg = PeakListDialog(None, _spectra())
    assert dlg.mark_tab is None and dlg.tabs.count() == 3


def test_marking_uses_the_settings_at_the_top_and_follows_them():
    dlg, plot = _window('mark')
    assert dlg.tabs.currentWidget() is dlg.mark_tab
    dlg.prominence.setValue(0.2)
    assert plot.marked == []                              # nothing marked before the button
    dlg.mark_button.click()
    s = plot.marked[-1]
    assert s['prominence'] == 0.2 and s['peak_mode'] == 'Positive' and s['labels'] == 'band'
    dlg.prominence.setValue(0.3)                           # the marks follow
    assert plot.marked[-1]['prominence'] == 0.3
    dlg.font_size_input.setValue(14)
    assert plot.marked[-1]['font_size'] == 14
    dlg.remove_marks_button.click()
    n = len(plot.marked)
    dlg.prominence.setValue(0.1)                           # removed: no longer followed
    assert plot.removed == 1 and len(plot.marked) == n


def test_the_list_is_found_when_its_tab_is_shown():
    """Opened on Mark on the plot (e.g. thousands of spectra of a map), the
    peaks are listed only when a tab of the list is shown."""
    dlg, _ = _window('mark')
    assert dlg.rows == [] and dlg.table.rowCount() == 0
    dlg.prominence.setValue(0.2)
    assert dlg.rows == []
    dlg.tabs.setCurrentIndex(0)
    assert dlg.table.rowCount() == 6 and len(dlg.rows) == 6


def test_reset_puts_back_the_numbers_on_the_plot_too():
    from src.views.dialogs.data_analysis.peak_detection_dialog import DEFAULTS
    dlg, _ = _window('mark', mark_settings={'labels': 'all', 'decimals': 5})
    assert dlg.mark_settings()['labels'] == 'all' and dlg.mark_settings()['decimals'] == 5
    dlg.reset_button.click()
    assert dlg.mark_settings() == DEFAULTS


def test_the_question_mark_explains_the_numbers_on_the_plot_too():
    dlg, _ = _window()
    dlg.help_button.click()
    text = dlg.settings_help.text.toPlainText()
    assert 'Labels' in text and 'Font size' in text and 'FWHM' in text


def test_the_controller_opens_the_right_tab_and_keeps_the_settings(tmp_path, monkeypatch):
    from src.controllers.data_analysis.peak_detection_controller import PeakDetectionController
    from src.views.dialogs.data_analysis.peak_list_dialog import PeakListDialog

    class Main:
        view = None
        static_canvas = None
        selected_spectra = _spectra()
    pdc = PeakDetectionController(Main())
    seen = []

    def run(dialog):
        seen.append(dialog.tabs.currentWidget() is dialog.mark_tab)
        dialog.decimals_input.setValue(4)
        dialog.prominence.setValue(0.25)
        return 0
    monkeypatch.setattr(PeakListDialog, 'exec_', run)
    pdc.show_dialog()                                       # Detect Peaks
    pdc.show_peak_list()                                    # Peak list...
    assert seen == [True, False]
    assert pdc.peak_decimals == 4 and pdc.peak_prominence == 0.25
