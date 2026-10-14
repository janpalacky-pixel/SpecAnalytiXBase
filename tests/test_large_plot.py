"""Plotting very many selected spectra: preview of an evenly spread subset,
"Plot all" drawn in portions with progress and Stop (large_selection.py,
large_plot_controller.py)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog, QPushButton, QLabel

from src.modules.visualization import large_selection as ls

app = QApplication.instance() or QApplication([])


# --- the rules (Qt-free) ------------------------------------------------------

def test_preview_is_evenly_spread_and_includes_both_ends():
    idx = ls.preview_indices(21000, 1000)
    assert len(idx) == 1000 and idx[0] == 0 and idx[-1] == 20999
    steps = np.diff(idx)
    assert steps.min() >= 20 and steps.max() <= 22
    assert ls.preview_indices(500, 1000) == list(range(500))


def test_which_plots_get_a_preview():
    s = {'threshold': 2000, 'preview_count': 1000, 'mode': 'preview'}
    for plot_type in ('Overlay plot', 'Grid plot', 'Waterfall plot'):
        assert ls.needs_preview(2001, plot_type, s)
        assert not ls.needs_preview(2000, plot_type, s)
        assert not ls.needs_preview(5000, plot_type, s, plot_all=True)
        assert not ls.needs_preview(5000, plot_type, dict(s, mode='all'))
    for plot_type in ('Heatmap', 'Mean ± SD', 'Difference', 'Single spectrum'):
        assert not ls.needs_preview(50000, plot_type, s)


def test_settings_are_kept_sensible():
    s = ls.normalized_settings({'threshold': 'x', 'preview_count': 99999, 'mode': 'weird'})
    assert s == dict(ls.DEFAULT_SETTINGS, preview_count=ls.DEFAULT_SETTINGS['threshold'])


# --- in the main window ---------------------------------------------------------

@pytest.fixture
def mc(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    for name in ('information', 'warning', 'critical'):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from src.controllers.core.main_controller import MainController
    controller = MainController()
    controller.large_plot_controller.set_settings(
        {'threshold': 300, 'preview_count': 100, 'mode': 'preview'})
    x = np.linspace(0, 100, 40)
    spectra = [{'label': f's{i:04d}', 'x_scale': x, 'y_scale': np.sin(x / 10) + i * 0.01,
                'metadata': {}} for i in range(1250)]
    controller.original_spectra = spectra
    controller.selected_spectra = list(spectra)
    controller.view.comboBox_plot_type_choice.setCurrentText('Overlay plot')
    yield controller
    controller.autosave_controller.shutdown()
    controller.view.deleteLater()


def _drawn(mc):
    return len(mc.static_canvas.spectrum_artists)


def _banner_text(mc):
    labels = mc.view.findChildren(QLabel, 'largePlotBannerText')
    return ' '.join(l.text() for l in labels)


def test_a_large_selection_shows_a_preview_and_keeps_the_selection(mc):
    mc.plot_spectra()
    assert _drawn(mc) == 100
    assert len(mc.selected_spectra) == 1250                      # analyses use all
    text = _banner_text(mc)
    assert 'Preview' in text and '100' in text and '1 250' in text


def test_plot_all_draws_everything_in_portions(mc, monkeypatch):
    mc.plot_spectra()
    portions = []
    real = QProgressDialog.setValue
    monkeypatch.setattr(QProgressDialog, 'setValue',
                        lambda self, v: portions.append(v) or real(self, v))
    mc.view.findChild(QPushButton, 'largePlotAllButton').click()
    assert _drawn(mc) == 1250
    assert portions[-1] == 1250 and 500 in portions               # drawn in portions
    assert all(a.get_visible() for g in mc.static_canvas.spectrum_artists for a in g)
    assert mc.interactive_mode_checkbox.isChecked()


def test_stop_keeps_what_is_drawn_and_switches_interactive_update_off(mc, monkeypatch):
    mc.plot_spectra()
    monkeypatch.setattr(QProgressDialog, 'wasCanceled', lambda self: True)   # Stop at once
    mc.large_plot_controller.request_plot_all()
    ax = mc.static_canvas.figure.axes[0]
    assert len(ax.lines) == 500                                   # first portion only
    assert not mc.interactive_mode_checkbox.isChecked()
    assert not mc.refresh_plot_button.isHidden()
    assert len(mc.selected_spectra) == 1250                       # selection untouched
    assert 'stopped' in _banner_text(mc) and '500' in _banner_text(mc)


def test_small_selections_and_other_plot_types_are_unchanged(mc):
    mc.selected_spectra = mc.original_spectra[:200]
    mc.plot_spectra()
    assert _drawn(mc) == 200
    assert mc.large_plot_controller.last_info['preview'] is False
    mc.selected_spectra = list(mc.original_spectra)
    mc.view.comboBox_plot_type_choice.setCurrentText('Heatmap')
    mc.plot_spectra()
    assert mc.large_plot_controller.last_info['preview'] is False


def test_always_plot_all_setting(mc):
    mc.large_plot_controller.set_settings({'threshold': 300, 'preview_count': 100, 'mode': 'all'})
    mc.plot_spectra()
    assert _drawn(mc) == 1250


def test_settings_dialog_round_trip():
    from src.controllers.visualization.large_plot_controller import LargePlotSettingsDialog
    d = LargePlotSettingsDialog({'threshold': 5000, 'preview_count': 800, 'mode': 'all'})
    assert d.settings() == {'threshold': 5000, 'preview_count': 800, 'mode': 'all'}
    d.preview_radio.setChecked(True)
    assert d.settings()['mode'] == 'preview'
