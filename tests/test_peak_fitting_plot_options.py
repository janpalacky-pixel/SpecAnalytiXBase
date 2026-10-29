"""Peak Fitting: the row above the plot. The plot takes all the free height;
Residual and Legend can be hidden (shown by default, remembered); with a
series, View (Overlay, Waterfall, Grid) works before the series is fitted."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

from src.modules.data_analysis.peak_fitting_manager import gaussian

app = QApplication.instance() or QApplication([])


def _series(n=4):
    x = np.linspace(0, 200, 401)
    return [{'label': f'scan : {i + 1:02d}', 'x_scale': x,
             'y_scale': gaussian(x, 1.0, 60 + 2 * i, 4.0) + gaussian(x, 0.4, 140, 6.0),
             'metadata': {}} for i in range(n)]


PEAKS = [{'model': 'Gaussian', 'center': 60.0, 'amplitude': 1.0, 'width': 4.0, 'color': '#1f77b4'},
         {'model': 'Gaussian', 'center': 140.0, 'amplitude': 0.4, 'width': 6.0, 'color': '#ff7f0e'}]


def _dialog(series=None, settings=None):
    from src.views.dialogs.data_analysis.peak_fitting_dialog import PeakFittingDialog
    sp = series or _series(1)
    dlg = PeakFittingDialog(None, spectrum=sp[0], current_settings=settings,
                            series=series)
    return dlg


def test_residual_and_legend_are_shown_and_can_be_hidden():
    dlg = _dialog()
    dlg.peaks = [dict(p) for p in PEAKS]
    dlg.update_plot()
    assert dlg.residual_check.isChecked() and dlg.legend_check.isChecked()
    assert len(dlg.figure.axes) == 2 and dlg.ax_main.get_legend() is not None
    dlg.residual_check.setChecked(False)
    assert len(dlg.figure.axes) == 1 and dlg.ax_residual is None
    assert dlg.ax_main.get_xlabel() == "X-Axis"
    dlg.legend_check.setChecked(False)
    assert dlg.ax_main.get_legend() is None
    settings = dlg.get_results()
    assert settings['show_residual'] is False and settings['show_legend'] is False
    again = _dialog(settings=settings)                       # remembered
    assert not again.residual_check.isChecked() and not again.legend_check.isChecked()
    again.residual_check.setChecked(True)
    assert len(again.figure.axes) == 2


def test_the_plot_takes_the_free_height():
    from PyQt5.QtWidgets import QSizePolicy
    dlg = _dialog(series=_series())
    layout = dlg.canvas.parentWidget().layout()
    assert layout.stretch(layout.indexOf(dlg.canvas)) == 1
    bar = dlg.residual_check.parentWidget()
    assert bar.sizePolicy().verticalPolicy() == QSizePolicy.Fixed
    assert bar is dlg.view_combo.parentWidget()               # one row: Spectra, ◀ ▶, View, options
    one = _dialog()
    assert one.residual_check.parentWidget().sizePolicy().verticalPolicy() == QSizePolicy.Fixed


def test_view_works_before_the_series_is_fitted():
    dlg = _dialog(series=_series())
    assert dlg.series_results is None and not dlg.view_combo.isEnabled()   # one selected
    dlg.list_all_button.click()                                # several: Overlay, data only
    assert dlg.view_combo.isEnabled()
    assert len(dlg.figure.axes) == 1 and len(dlg.figure.axes[0].lines) == 4
    assert 'fit' not in dlg.figure.axes[0].get_title()
    dlg.view_combo.setCurrentIndex(2)                          # Grid
    assert len(dlg.figure.axes) == 4
    assert all('not fitted' not in ax.get_title() for ax in dlg.figure.axes)
    dlg.legend_check.setChecked(False)
    dlg.view_combo.setCurrentIndex(0)                          # Overlay
    assert dlg.figure.axes[0].get_legend() is None
    dlg.show_series_spectrum(1)
    assert len(dlg.figure.axes) == 2                           # one spectrum + residual
