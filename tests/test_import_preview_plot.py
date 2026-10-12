"""Import dialog: plot preview of what Import would read, JASCO channel
values table, and the channel-type guess."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import glob
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from src.modules.data_io import jasco_jws_reader as reader

app = QApplication.instance() or QApplication([])
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'resources', 'test_data')
JWB = sorted(glob.glob(os.path.join(DATA, 'real', 'CD melting', '*.jwb')))[0]
TBA = os.path.join(DATA, 'real', 'CD_spectra_TBA.txt')
XLSX = os.path.join(DATA, 'synthetic', 'cd_2comp_clean.xlsx')


# --- channel-type guess ------------------------------------------------------

@pytest.mark.parametrize('values, expected', [
    ([275, 973], 'HT'),                    # hundreds of volts, never negative
    ([-23, 25.7], 'CD'),                   # both signs
    ([-120, 80], 'CD'),                    # large CD is still CD (was "Signal")
    ([-3, -0.8], 'CD'),                    # clearly negative only
    ([1.07, 5.14], 'Abs'),                 # raw JASCO absorbance
    ([0.05, 1.8], 'Abs'),
    ([2, 25], 'CD'),                       # positive only, too large for absorbance
    ([0.5, 6.5], 'Abs'),                   # the honest ambiguity: small positive -> Abs
])
def test_channel_guess(values, expected):
    assert reader._classify_channel(np.linspace(*values, 50)) == expected


def test_sample_files_still_guessed_correctly():
    for path in glob.glob(os.path.join(DATA, 'real', 'CD melting', '*.jwb')):
        probe = reader.probe_jwb_channels(path)
        assert [c['type'] for c in probe['channels']] == ['CD', 'Abs']


# --- dialog ------------------------------------------------------------------

@pytest.fixture
def make_dialog(monkeypatch, tmp_path):
    monkeypatch.setenv('SPECANALYTIXBASE_DATA_DIR', str(tmp_path / 'appdata'))
    from src.views.dialogs.misc import import_dialog as mod
    monkeypatch.setattr(mod, 'ImportProfileManager', MagicMock())
    made = []

    def make(path):
        dlg = mod.ImportDialog(None, [path], {})
        dlg._plot_timer.stop()
        dlg._update_plot_preview()
        made.append(dlg)
        return dlg
    yield make
    for dlg in made:
        dlg.deleteLater()


def _panels(dlg):
    return [ax for ax in dlg._plot_canvas.fig.axes if ax.lines]


def test_jwb_values_table_and_plot(make_dialog):
    dlg = make_dialog(JWB)
    table = dlg._preview_table
    headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    assert headers == ['wavelength (nm)', 'Channel 1: CD [mdeg]', 'Channel 2: Absorbance [AU]']
    assert table.rowCount() == 12
    xs = [float(table.item(r, 0).text()) for r in range(table.rowCount())]
    assert min(xs) < 230 and max(xs) > 470           # spread over the whole range
    assert dlg._jws_channels_table.horizontalHeaderItem(1).text() == 'Type (guessed)'
    assert 'guessed' in dlg._jws_guess_note.text()
    panels = _panels(dlg)
    assert len(panels) == 2                          # one per channel (different units)
    assert 'CD' in panels[0].get_title() and 'Absorbance' in panels[1].get_title()
    assert len(panels[0].lines) == reader.probe_jwb_channels(JWB)['n_spectra']  # every temperature


def test_changing_a_type_or_unticking_updates_headers_and_plot(make_dialog):
    from PyQt5.QtCore import Qt
    dlg = make_dialog(JWB)
    dlg._jws_channels_table.cellWidget(1, 1).setCurrentText('Signal')
    assert dlg._preview_table.horizontalHeaderItem(2).text() == 'Channel 2: Signal  ⚠'
    dlg._jws_channels_table.item(1, 0).setCheckState(Qt.Unchecked)
    dlg._plot_timer.stop()
    dlg._update_plot_preview()
    assert len(_panels(dlg)) == 1


@pytest.mark.parametrize('path', [TBA, XLSX])
def test_text_and_excel_files_are_plotted(make_dialog, path):
    dlg = make_dialog(path)
    (panel,) = _panels(dlg)
    assert 1 <= len(panel.lines) <= 30


def test_the_plot_follows_the_settings(make_dialog):
    dlg = make_dialog(TBA)
    n_before = len(_panels(dlg)[0].lines)
    dlg._layout_row.setChecked(True)                 # nonsense layout for this file
    dlg._plot_timer.stop()
    dlg._update_plot_preview()
    after = _panels(dlg)
    assert not after or len(after[0].lines) != n_before


def test_plot_can_be_switched_off_and_large_files_wait(make_dialog, monkeypatch):
    dlg = make_dialog(TBA)
    dlg._plot_cb.setChecked(False)
    assert dlg._plot_canvas.isHidden()
    from src.modules.misc.session_files import Preferences
    assert Preferences().get('import_plot_preview') is False
    dlg._plot_cb.setChecked(True)
    monkeypatch.setattr(type(dlg), '_PLOT_AUTO_MAX_BYTES', 10)
    dlg._update_plot_preview()
    assert _panels(dlg) == [] and not dlg._plot_now_btn.isHidden()
    dlg._update_plot_preview(force=True)
    assert _panels(dlg)


def test_a_type_that_contradicts_the_values_is_flagged(make_dialog):
    dlg = make_dialog(JWB)
    assert dlg._jws_type_warning.isHidden()
    dlg._jws_channels_table.cellWidget(1, 1).setCurrentText('CD [mdeg]')
    header = dlg._preview_table.horizontalHeaderItem(2).text()
    assert header == 'Channel 2: CD [mdeg]  ⚠'
    text = dlg._jws_type_warning.text()
    assert not dlg._jws_type_warning.isHidden()
    assert 'look like Absorbance' in text and 'both set to CD [mdeg]' in text
    assert 'numbers stay the same' in text
    dlg._jws_channels_table.cellWidget(1, 1).setCurrentText('Absorbance [AU]')
    assert dlg._jws_type_warning.isHidden()
    assert dlg._preview_table.horizontalHeaderItem(2).text() == 'Channel 2: Absorbance [AU]'


def test_two_channels_with_the_same_type_get_distinct_names():
    spectra = reader.read_jwb_data(JWB, channel_type_overrides={0: 'CD', 1: 'CD'})
    labels = [s['label'] for s in spectra]
    assert len(set(labels)) == len(labels)
    assert ' : CD [mdeg] ch1 T=' in labels[0] and ' : CD [mdeg] ch2 T=' in labels[-1]
    normal = reader.read_jwb_data(JWB)
    assert ' : CD [mdeg] T=' in normal[0]['label']       # unchanged when types differ
