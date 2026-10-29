"""Peak Fitting window: the orange "?" buttons (short help, each with a link
to its section of the full help); Residual and Legend only where they apply;
Add via Click and the toolbar's Zoom/Pan switch each other off; a clicked
peak gets the width of the band; with a series, Add for chooses which fitted
spectra get the output spectra."""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.modules.data_analysis.peak_fitting_manager import gaussian

app = QApplication.instance() or QApplication([])


def _series(n=4):
    x = np.linspace(0, 200, 401)
    return [{'label': f'scan : {i + 1:02d}', 'x_scale': x,
             'y_scale': gaussian(x, 1.0, 60 + 2 * i, 4.0) + gaussian(x, 0.4, 140, 6.0),
             'metadata': {}} for i in range(n)]


PEAKS = [{'model': 'Gaussian', 'center': 60.0, 'amplitude': 1.0, 'width': 4.0, 'color': '#1f77b4'},
         {'model': 'Gaussian', 'center': 140.0, 'amplitude': 0.4, 'width': 6.0, 'color': '#ff7f0e'}]


def _window(series=None):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = series or _series(1)
    dlg = PeakFittingDialog(None, spectrum=sp[0], series=series)
    if series:
        dlg.follow_check.setChecked(True)                        # peaks on the first only
    dlg.peaks = [dict(p) for p in PEAKS]
    dlg.update_peaks_table()
    return dlg


def test_every_quick_help_has_a_button_and_its_section_in_the_help():
    from src.help.peak_fitting_quick_help import QUICK_HELP
    from src.help.peak_fitting_help import get_peak_fitting_help_content
    page = get_peak_fitting_help_content()
    ids = set(re.findall(r'id="([^"]+)"', page))
    dlg = _window(_series())
    assert set(dlg.quick_help_buttons) == set(QUICK_HELP)
    for key, (title, anchor, html) in QUICK_HELP.items():
        assert anchor in ids, anchor
        assert dlg.quick_help_buttons[key].text() == '?'
        box = dlg.show_quick_help(key, run=False)
        assert box.windowTitle() == title and 'Full help' in box.buttons()[0].text() + \
            ''.join(b.text() for b in box.buttons())
    one = _window()
    assert 'series' not in one.quick_help_buttons or one.start_widget.isHidden()


def test_residual_and_legend_only_where_they_apply():
    dlg = _window(_series())
    assert dlg.residual_check.isEnabled() and dlg.legend_check.isEnabled()
    dlg.list_all_button.click()                                  # Overlay
    assert not dlg.residual_check.isEnabled() and dlg.legend_check.isEnabled()
    dlg.legend_check.setChecked(False)
    assert dlg.figure.axes[0].get_legend() is None
    dlg.legend_check.setChecked(True)
    assert dlg.figure.axes[0].get_legend() is not None
    dlg.view_combo.setCurrentIndex(2)                            # Grid
    assert not dlg.legend_check.isEnabled()
    dlg.show_series_spectrum(0)
    assert dlg.residual_check.isEnabled() and dlg.legend_check.isEnabled()


def test_add_via_click_and_zoom_pan_switch_each_other_off():
    dlg = _window()
    dlg.interactive_add_cb.setChecked(True)
    assert dlg.toolbar.isEnabled() and 'adds a peak' in dlg.click_hint.text()
    dlg.toolbar.zoom()                                           # choose Zoom
    assert not dlg.interactive_add_cb.isChecked()
    assert 'off' in dlg.click_hint.text()
    dlg.interactive_add_cb.setChecked(True)                      # Add via Click again
    assert not str(dlg.toolbar.mode)
    dlg.toolbar.pan()
    assert not dlg.interactive_add_cb.isChecked()


def test_a_clicked_peak_gets_the_width_of_the_band():
    dlg = _window()
    dlg.peaks = []
    dlg.interactive_add_cb.setChecked(True)
    dlg.update_plot()

    class Click:
        button = 1
        xdata, ydata = 140.5, 0.4

        def __init__(self):
            self.inaxes = dlg.ax_main                            # the plot is redrawn each time
    dlg.on_canvas_click(Click())
    assert dlg.peaks[-1]['width'] == pytest.approx(6.0, rel=0.1)
    dlg.initial_peak_width = 2.5                                  # set by the user: kept
    dlg.width_set_by_user = True
    dlg.on_canvas_click(Click())
    assert dlg.peaks[-1]['width'] == 2.5


def test_add_for_the_selected_fitted_spectra():
    dlg = _window(_series())
    dlg.fit_all_selected()
    assert dlg.output_for_combo.itemText(0) == 'all fitted spectra (4)'
    lst = dlg.spectra_list
    lst.clearSelection()
    for r in (1, 3):
        lst.selectionModel().select(lst.model().index(r, 0), QItemSelectionModel.Select)
    assert dlg.output_for_combo.itemText(1).endswith('(2)')
    assert dlg.get_results()['output_labels'] == [s['label'] for s in dlg.series]
    dlg.output_for_combo.setCurrentIndex(1)
    assert dlg.get_results()['output_labels'] == ['scan : 02', 'scan : 04']
    assert dlg.get_results()['output_for'] == 'selected'


def test_ok_adds_the_outputs_for_the_chosen_spectra_only(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    said = []
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name,
                            staticmethod(lambda *a, **k: said.append(a[2]) or QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    from src.controllers.data_analysis.peak_fitting_controller import PeakFittingController
    from src.views.dialogs.misc import import_dialog
    monkeypatch.setattr(import_dialog.ImportDialog, 'run', staticmethod(
        lambda view, settings, file_paths=None: (True, list(file_paths), [{} for _ in file_paths])))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mc = MainController()
    try:
        mc.import_controller._run_import(clear_first=True, file_paths=[
            os.path.join(root, 'resources', 'test_data', 'real', 'CD_spectra_TBA.txt')])
        mc.spectrum_selector.select_all_items()
        app.processEvents()
        n0 = len(mc.original_spectra)
        labels = [s['label'] for s in mc.original_spectra[:3]]
        peak = [{'model': 'Gaussian', 'parameters': {'center': 260.0, 'height': 1.0, 'sigma': 5.0,
                                                     'fwhm': 11.77, 'area': 12.53}}]
        results = [{'label': lab, 'ok': True, 'peaks': peak, 'r2': 0.9} for lab in labels]
        settings = {'fit_results': peak, 'spectrum_label': labels[0], 'series_results': results,
                    'output_options': {'add_fit': True}, 'output_labels': [labels[2]]}
        mc.operations_controller.current_parameters['Peak Fitting'] = settings
        PeakFittingController(mc).handle_peak_fitting()
        now = [s['label'] for s in mc.original_spectra]
        assert len(now) == n0 + 1 and labels[2] + '_fit' in now
        settings['output_labels'] = []                           # none chosen: a message
        PeakFittingController(mc).handle_peak_fitting()
        assert len(mc.original_spectra) == n0 + 1 and 'None of the spectra' in said[-1]
    finally:
        mc.autosave_controller.shutdown()
        mc.view.deleteLater()
