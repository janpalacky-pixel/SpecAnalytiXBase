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


# --- legend with more entries than "Maximum Legend Items" ------------------------

def _legend_texts(mc):
    leg = mc.static_canvas.figure.axes[0].get_legend()
    return [t.get_text() for t in leg.get_texts()]


def _legend_note(mc):
    return ' '.join(l.text() for l in mc.view.findChildren(QLabel, 'legendBannerText'))


def test_legend_lists_an_evenly_spread_subset_with_a_note(mc):
    mc.legend_manager.update_settings({'visible': True})
    mc.selected_spectra = mc.original_spectra[:50]
    mc.plot_spectra()
    texts = _legend_texts(mc)
    assert len(texts) == 20 and texts[0] == 's0000' and texts[-1] == 's0049'
    assert 'Legend: 20 of 50 spectra listed (evenly spread)' in _legend_note(mc)
    # with a preview: entries of the drawn spectra, both notes in one strip
    mc.selected_spectra = list(mc.original_spectra)
    mc.plot_spectra()
    assert 'Legend: 20 of 100 drawn spectra' in _legend_note(mc)
    assert 'Preview' in _banner_text(mc)
    assert len(mc.view.findChildren(QPushButton, 'largePlotAllButton')) == 1
    # few spectra or no legend: no note
    mc.selected_spectra = mc.original_spectra[:10]
    mc.plot_spectra()
    assert _legend_note(mc) == '' and len(_legend_texts(mc)) == 10
    mc.legend_manager.update_settings({'visible': False})
    mc.selected_spectra = mc.original_spectra[:50]
    mc.plot_spectra()
    assert _legend_note(mc) == ''


def test_legend_show_all_and_choose(mc, monkeypatch):
    mc.legend_manager.update_settings({'visible': True})
    mc.selected_spectra = mc.original_spectra[:50]
    mc.plot_spectra()
    mc.view.findChild(QPushButton, 'legendShowAllButton').click()
    assert len(_legend_texts(mc)) == 50 and _legend_note(mc) == ''
    assert mc.legend_manager.current_settings['show_all_items'] is True     # stays on
    mc.plot_spectra()
    assert len(_legend_texts(mc)) == 50
    mc.legend_manager.update_settings({'show_all_items': False})
    mc.plot_spectra()
    # Choose...: the Select spectra window, here every 10th entry
    from src.views.dialogs.misc import spectra_selection_dialog as ssd
    monkeypatch.setattr(ssd.SpectraSelectionDialog, 'exec_', lambda self: 1)
    monkeypatch.setattr(ssd.SpectraSelectionDialog, 'get_selection_parameters',
                        lambda self: {'indices': list(range(0, 50, 10)), 'action': 'select'})
    mc.view.findChild(QPushButton, 'legendChooseButton').click()
    assert _legend_texts(mc) == ['s0000', 's0010', 's0020', 's0030', 's0040']
    assert 'Legend: 5 of 50 spectra listed (your choice)' in _legend_note(mc)
    mc.plot_spectra()                                       # same spectra: kept
    assert len(_legend_texts(mc)) == 5
    mc.view.findChild(QPushButton, 'legendAutoButton').click()
    assert len(_legend_texts(mc)) == 20
    mc.view.findChild(QPushButton, 'legendChooseButton').click()
    mc.selected_spectra = mc.original_spectra[:60]          # other spectra: forgotten
    mc.plot_spectra()
    assert len(_legend_texts(mc)) == 20


def test_legend_show_all_asks_above_500(mc, monkeypatch):
    mc.large_plot_controller.set_settings({'threshold': 5000, 'preview_count': 100,
                                           'mode': 'preview'})
    mc.legend_manager.update_settings({'visible': True})
    mc.selected_spectra = mc.original_spectra[:600]
    mc.plot_spectra()
    asked = []
    monkeypatch.setattr(QMessageBox, 'question',
                        staticmethod(lambda *a, **k: asked.append(1) or QMessageBox.No))
    mc.large_plot_controller.legend_show_all()
    assert asked and len(_legend_texts(mc)) == 20
    assert mc.legend_manager.current_settings['show_all_items'] is False


def test_show_legend_checkbox_in_basic_plot_options(mc):
    """The legend is on by default; 'show legend' (Basic plot options) hides
    and shows it without plotting again; the Legend window no longer has its
    own Show Legend checkbox and keeps the checkbox's choice."""
    from src.views.dialogs.visualization.legend_properties_dialog import LegendPropertiesDialog
    assert mc.legend_manager.current_settings['visible'] is True
    assert mc.legend_checkbox is mc.view.show_legend_checkBox and mc.legend_checkbox.isChecked()
    mc.selected_spectra = mc.original_spectra[:10]
    mc.plot_spectra()
    ax = mc.static_canvas.figure.axes[0]
    assert ax.get_legend().get_visible()
    mc.legend_checkbox.setChecked(False)
    assert mc.static_canvas.figure.axes[0] is ax              # not plotted again
    assert not ax.get_legend().get_visible()
    assert mc.legend_manager.current_settings['visible'] is False
    mc.plot_spectra()
    leg = mc.static_canvas.figure.axes[0].get_legend()
    assert leg is None or not leg.get_visible()
    d = LegendPropertiesDialog(settings=mc.legend_manager.get_current_settings())
    assert not hasattr(d, 'visible_cb')
    assert d.get_settings()['visible'] is False
    d.reset_to_default()
    assert d.get_settings()['visible'] is False                # Reset keeps show / hide
    mc.legend_checkbox.setChecked(True)
    assert mc.static_canvas.figure.axes[0].get_legend().get_visible()


def test_snapshot_restore_updates_the_show_legend_checkbox(mc):
    from src.modules.misc.save_spectra_manager import SaveManager
    SaveManager()._restore_plot_appearance(mc, {'legend': {'visible': False}})
    assert not mc.legend_checkbox.isChecked()
    SaveManager()._restore_plot_appearance(mc, {})
    assert mc.legend_checkbox.isChecked()
