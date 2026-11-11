"""Save plot for publication in the tool windows whose plots are results
(Peak Fitting, SVD, PCA, MCR-ALS, NMF, Group Statistics, Melting curve,
Kinetics, 2D correlation, ...): their plot toolbars come from
src/views/plot_toolbar.py and have the button; it opens the same window as
for the main plot with a copy of that plot. The processing windows (their
plots are previews) keep matplotlib's own toolbar. The smoke test
(test_smoke_all_tools) makes a picture of every such plot on real data."""
import glob
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
matplotlib.use('Agg')
import pytest
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QVBoxLayout

app = QApplication.instance() or QApplication([])
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

from src.views import publication_actions as pa
from src.views.plot_toolbar import NavigationToolbar

RESULT_WINDOWS = [
    'visualization_analysis/band_ratio_dialog.py', 'visualization_analysis/cluster_analysis_dialog.py',
    'visualization_analysis/isosbestic_point_dialog.py',
    'visualization_analysis/kinetics_fitting_dialog.py', 'visualization_analysis/mcr_als_dialog.py',
    'visualization_analysis/melting_curve_dialog.py', 'visualization_analysis/nmf_dialog.py',
    'visualization_analysis/pca_scores_dialog.py', 'visualization_analysis/pls_dialog.py',
    'visualization_analysis/qc_outlier_dialog.py',
    'visualization_analysis/reference_matching_dialog.py',
    'visualization_analysis/roi_spectra_dialogs.py', 'visualization_analysis/som_dialog.py',
    'visualization_analysis/svd_analysis_dialog.py',
    'visualization_analysis/two_d_correlation_dialog.py',
    'data_analysis/peak_fitting_dialog.py', 'data_analysis/peak_list_dialog.py',
    'data_analysis/mixture_analysis_dialog.py']


def _window_with_plot(title="Kinetics Fitting", plot=True):
    dlg = QDialog()
    dlg.setWindowTitle(title)
    fig = Figure()
    canvas = FigureCanvasQTAgg(fig)
    tb = NavigationToolbar(canvas, dlg)
    lay = QVBoxLayout(dlg)
    lay.addWidget(tb)
    lay.addWidget(canvas)
    ax = fig.add_subplot(111)
    if plot:
        ax.plot([1, 2, 3], [2, 1, 3], label='data')
    else:
        ax.text(0.5, 0.5, "Press Run")
    return dlg, tb, fig


def test_the_toolbar_has_the_button_after_save():
    dlg, tb, fig = _window_with_plot()
    names = [a.objectName() for a in tb.actions()]
    assert 'publicationButton' in names
    save = tb._actions['save_figure']
    assert tb.actions()[tb.actions().index(save) + 1] is tb.publication_action
    dlg.deleteLater()


def test_the_button_opens_the_window_with_the_tools_name(monkeypatch):
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    opened = []
    monkeypatch.setattr(PublicationDialog, 'exec_',
                        lambda self: opened.append(self.windowTitle()) or QDialog.Rejected)
    dlg, tb, fig = _window_with_plot("Kinetics Fitting")
    assert tb.save_for_publication() is not None
    assert opened == ["Save plot for publication – Kinetics Fitting"]
    dlg.deleteLater()


def test_no_plot_yet_a_message(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, 'information',
                        staticmethod(lambda *a, **k: shown.append(a[2]) or QMessageBox.Ok))
    dlg, tb, fig = _window_with_plot(plot=False)
    assert tb.save_for_publication() is None
    assert shown and 'no plot' in shown[0]
    dlg.deleteLater()


def test_what_is_drawn_only_for_the_moment_is_left_out():
    """A range being dragged (matplotlib's selectors, drawn 'animated' with
    blitting) is not in the picture; the plot on the screen is untouched."""
    from src.modules.visualization import publication_figure as pf
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1], label='data')
    span = ax.axvspan(0.2, 0.4, animated=True)
    copy = pa.plot_copy(fig)
    assert span.get_gid() is None
    out = pf.copy_for_publication(copy, 8.5, 6.5, font_pt=7)
    assert not any(p.get_animated() for p in out.axes[0].patches)


@pytest.mark.parametrize('path', RESULT_WINDOWS)
def test_result_windows_use_the_toolbar_with_the_button(path):
    text = open(os.path.join(ROOT, 'src', 'views', 'dialogs', path), encoding='utf-8').read()
    assert 'from src.views.plot_toolbar import NavigationToolbar' in text, path
    assert not re.search(r'import [^\n]*NavigationToolbar2QT', text), path


def test_processing_windows_keep_matplotlibs_toolbar():
    """Previews (the result is saved from the main plot): no button there."""
    for path in glob.glob(os.path.join(ROOT, 'src', 'views', 'dialogs', 'data_analysis', '*.py')):
        rel = 'data_analysis/' + os.path.basename(path)
        if rel in RESULT_WINDOWS:
            continue
        text = open(path, encoding='utf-8').read()
        assert 'plot_toolbar' not in text, rel


def test_group_statistics_has_publication_buttons():
    text = open(os.path.join(ROOT, 'src', 'views', 'dialogs', 'visualization_analysis',
                             'group_statistics_dialog.py'), encoding='utf-8').read()
    assert text.count('self._publication_button(') == 2


def test_mixture_analysis_before_calculate_says_no_plot_yet(monkeypatch):
    """The scenario in the help: Mixture analysis opened, Calculate not
    pressed yet, the Publication icon clicked - a message, no empty window."""
    import numpy as np
    from src.views.dialogs.data_analysis.mixture_analysis_dialog import MixtureAnalysisDialog
    from src.views.dialogs.visualization.publication_dialog import PublicationDialog
    shown, opened = [], []
    monkeypatch.setattr(QMessageBox, 'information',
                        staticmethod(lambda *a, **k: shown.append(a[2]) or QMessageBox.Ok))
    monkeypatch.setattr(PublicationDialog, 'exec_', lambda self: opened.append(1) or 0)
    x = np.linspace(400, 1800, 200)
    spectra = [{'label': f's{i}', 'x_scale': x, 'y_scale': np.exp(-((x - 800 - 50 * i) / 30) ** 2),
                'metadata': {}} for i in range(3)]
    dlg = MixtureAnalysisDialog(None, spectra)
    tb = dlg.findChild(NavigationToolbar)
    tb.publication_action.trigger()
    assert opened == [] and shown and 'no plot' in shown[-1]
    dlg.deleteLater()
