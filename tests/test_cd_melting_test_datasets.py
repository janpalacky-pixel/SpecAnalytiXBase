"""Help -> Test datasets -> Real (measured) -> CD melting (JASCO .jwb):
every menu entry points at a shipped file that imports, and Melting Curve
Analysis reads the right temperature from the resulting labels."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib

import pytest
from PyQt5.QtWidgets import QApplication

from src.modules.data_io import jasco_jws_reader as reader
from src.views.main_window import REAL_TEST_DATASETS_CD_MELTING

app = QApplication.instance() or QApplication([])
REAL_DIR = pathlib.Path(__file__).resolve().parent.parent / 'resources' / 'test_data' / 'real'


def _path(fname):
    return REAL_DIR.joinpath(*fname.split('/'))


def test_there_are_three_cd_melting_datasets():
    assert len(REAL_TEST_DATASETS_CD_MELTING) == 3


@pytest.mark.parametrize('label, fname', REAL_TEST_DATASETS_CD_MELTING)
def test_each_file_is_shipped_and_imports(label, fname):
    path = _path(fname)
    assert path.exists(), f'{fname} missing from resources/test_data/real'
    info = reader.probe_jwb_channels(str(path))
    assert info['n_spectra'] >= 15 and len(info['channels']) == 2
    expected = 'cooling' if 'cooling' in fname else 'heating'
    assert info['direction'] == expected and expected in label
    spectra = reader.read_jwb_data(str(path), selected_channels=[0, 1])
    assert len(spectra) == 2 * info['n_spectra']
    assert len({s['label'] for s in spectra}) == len(spectra)          # labels unique


@pytest.mark.parametrize('label, fname', REAL_TEST_DATASETS_CD_MELTING)
def test_melting_curve_reads_the_temperature_not_the_file_name_numbers(label, fname):
    from src.views.dialogs.visualization_analysis import melting_curve_dialog as m
    spectra = reader.read_jwb_data(str(_path(fname)), selected_channels=[0])
    numbers = [m._NUMBER_RE.findall(s['label']) for s in spectra]
    pos = m.MeltingCurveDialog._pick_varying_number_position(None, numbers)
    got = [float(n[pos]) for n in numbers]
    true = [s['metadata']['temperature_C'] for s in spectra]
    assert got == pytest.approx(true, abs=0.006)


def test_menu_has_a_cd_melting_submenu_with_the_three_entries():
    from src.views.main_window import MainWindow
    win = MainWindow(None)
    titles = [a.text() for a in win.menuHelpTestDatasetsCDMelting.actions()]
    assert titles == [label for label, _ in REAL_TEST_DATASETS_CD_MELTING]
    for _, fname in REAL_TEST_DATASETS_CD_MELTING:
        assert fname in win.real_dataset_actions
