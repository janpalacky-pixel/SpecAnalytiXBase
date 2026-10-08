"""Import of JASCO .jwb temperature scans (e.g. CD melting experiments).

A .jwb file is the same OLE2 container as .jws but holds one spectrum per
temperature. Real files were checked once against an independent
olefile-based reader (identical temperatures and values for all channels of
three real scans); these tests use small synthetic streams so they need no
data file: the OLE container reader is replaced by one returning the three
streams a real file contains (DataInfo, Y-Data, SampleInfo), laid out the
way the real files are.
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import struct
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from src.modules.data_io import jasco_jws_reader as reader
from src.modules.core.spectrum_manager import SpectrumManager

X_FIRST, X_LAST, N_POINTS = 480.0, 220.0, 27   # scanned downwards, like the real files


def _streams(temps, n_channels=2, n_points=N_POINTS, drop_bytes=0):
    n_spectra = len(temps)
    info = struct.pack('<6I', 0, n_spectra, 0, n_channels, 0, n_points)
    info += struct.pack('<3d', X_FIRST, X_LAST, -(X_FIRST - X_LAST) / (n_points - 1))
    info += b'\x00' * (96 - len(info)) + struct.pack(f'<{n_spectra}d', *temps)
    t = np.arange(n_spectra)[:, None]
    p = np.arange(n_points)[None, :]
    cd = (np.sin(p / 4.0) * (5 + t)).astype('<f4')           # straddles zero  -> CD
    ab = (1.5 + 0.01 * t + 0.001 * p).astype('<f4')          # small, positive -> Absorbance
    y = np.stack([cd, ab])[:n_channels]
    ydata = y.tobytes()
    sample = b'\x07\x00\x01\x00' + 'sample-A\x00\x00\x0010K'.encode('utf-16-le')
    return {'DataInfo': info, 'Y-Data': ydata[:len(ydata) - drop_bytes], 'SampleInfo': sample}, y


@pytest.fixture
def jwb_file(tmp_path, monkeypatch):
    """Returns make(temps, **kw) -> path of a dummy .jwb file whose 'contents'
    (as the patched container reader sees them) are the synthetic streams."""
    made = {}

    def make(temps, name='run1.jwb', **kw):
        streams, y = _streams(temps, **kw)
        path = tmp_path / name
        path.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 32)
        made[str(path)] = streams
        return str(path), y

    def fake_read(data, wanted):
        return dict(made[fake_read.current])

    # open() is real, so route by the path of the file being read.
    real_open = open

    def tracking_open(p, *a, **k):
        fake_read.current = str(p)
        return real_open(p, *a, **k)

    monkeypatch.setattr(reader, '_read_ole_streams', fake_read)
    monkeypatch.setattr(reader, 'open', tracking_open, raising=False)
    return make


TEMPS = [10.04, 20.01, 30.0, 40.02]


class TestReadJwbData:

    def test_one_spectrum_per_channel_and_temperature(self, jwb_file):
        path, y = jwb_file(TEMPS)
        spectra = reader.read_jwb_data(path)
        assert len(spectra) == 2 * len(TEMPS)
        # channel by channel, temperatures in measured order
        assert [s['label'] for s in spectra[:4]] == [
            'run1 : CD [mdeg] T=10.04C', 'run1 : CD [mdeg] T=20.01C',
            'run1 : CD [mdeg] T=30.00C', 'run1 : CD [mdeg] T=40.02C']
        assert spectra[4]['label'] == 'run1 : Absorbance [AU] T=10.04C'
        np.testing.assert_allclose(spectra[1]['y_scale'], y[0][1], rtol=1e-6)
        np.testing.assert_allclose(spectra[5]['y_scale'], y[1][1], rtol=1e-6)
        np.testing.assert_allclose(spectra[0]['x_scale'][[0, -1]], [X_FIRST, X_LAST])
        assert len(spectra[0]['x_scale']) == N_POINTS

    def test_metadata_carries_temperature_direction_and_file_text(self, jwb_file):
        path, _ = jwb_file(TEMPS)
        md = reader.read_jwb_data(path)[2]['metadata']
        assert md['file_type'] == 'jasco_jwb'
        assert md['temperature_C'] == pytest.approx(30.0)
        assert md['direction'] == 'heating'
        assert md['jasco_sample_name'] == 'sample-A' and md['jasco_comment'] == '10K'
        ip = md['import_parameters']
        assert (ip['channel_index'], ip['channel_type'], ip['spectrum_index'], ip['n_spectra_in_file']) == (0, 'CD', 2, 4)

    def test_cooling_scan_is_recognised(self, jwb_file):
        path, _ = jwb_file([86.5, 70.0, 50.0, 5.0])
        assert reader.read_jwb_data(path)[0]['metadata']['direction'] == 'cooling'

    def test_channel_selection_and_type_override(self, jwb_file):
        path, _ = jwb_file(TEMPS)
        only_abs = reader.read_jwb_data(path, selected_channels=[1])
        assert len(only_abs) == 4 and all('Absorbance' in s['label'] for s in only_abs)
        forced = reader.read_jwb_data(path, selected_channels=[1], channel_type_overrides={1: 'Signal'})
        assert forced[0]['label'] == 'run1 : Signal T=10.04C'
        assert forced[0]['metadata']['import_parameters']['channel_type_auto_detected'] is False

    def test_repeated_temperature_gets_unique_labels(self, jwb_file):
        # Labels are the dictionary key spectra are stored under, so a hold at
        # one temperature must not silently overwrite itself.
        path, _ = jwb_file([20.0, 20.0, 20.0, 30.0], name='hold.jwb')
        labels = [s['label'] for s in reader.read_jwb_data(path, selected_channels=[0])]
        assert len(set(labels)) == 4
        assert labels[:3] == ['hold : CD [mdeg] T=20.00C', 'hold : CD [mdeg] T=20.00C #2',
                              'hold : CD [mdeg] T=20.00C #3']

    def test_probe_describes_the_file_for_the_dialog(self, jwb_file):
        path, _ = jwb_file(TEMPS)
        p = reader.probe_jwb_channels(path)
        assert (p['n_spectra'], p['n_points'], p['direction']) == (4, N_POINTS, 'heating')
        assert (p['t_first'], p['t_last']) == (pytest.approx(10.04), pytest.approx(40.02))
        assert [c['type'] for c in p['channels']] == ['CD', 'Abs']

    @pytest.mark.parametrize("kwargs, text", [
        ({'drop_bytes': 4}, "does not match"),
    ])
    def test_inconsistent_file_is_rejected_with_a_reason(self, jwb_file, kwargs, text):
        path, _ = jwb_file(TEMPS, **kwargs)
        with pytest.raises(ValueError, match=text):
            reader.read_jwb_data(path)

    def test_missing_streams_are_rejected(self, jwb_file, monkeypatch):
        path, _ = jwb_file(TEMPS)
        monkeypatch.setattr(reader, '_read_ole_streams', lambda data, wanted: {})
        with pytest.raises(ValueError, match="DataInfo/Y-Data"):
            reader.read_jwb_data(path)

    def test_not_an_ole_file_is_rejected(self, tmp_path):
        p = tmp_path / 'junk.jwb'
        p.write_bytes(b'this is not a JASCO file at all')
        with pytest.raises(ValueError, match=r"\.jwb"):
            reader.read_jwb_data(str(p))


class TestSpectrumManagerIntegration:

    def test_extension_is_registered(self):
        assert '.jwb' in SpectrumManager.SUPPORTED_EXTENSIONS

    def test_full_import_pipeline(self, jwb_file):
        path, _ = jwb_file(TEMPS)
        mgr = SpectrumManager()
        mgr.load_spectrum_from_file(path, jws_selected_channels=[0])
        assert len(mgr.spectra) == len(TEMPS)
        for s in mgr.spectra.values():
            assert np.all(np.diff(s.x_scale) >= 0)          # app-wide ascending-x rule
            assert s.metadata['file_type'] == 'jasco_jwb'
            assert 'unique_id' in s.metadata


class TestMeltingCurveFindsTheTemperature:

    def test_label_temperature_is_the_number_that_varies(self, jwb_file):
        """Melting Curve Analysis guesses each spectrum's temperature from the
        label; the new labels must make it pick the temperature, not the
        digits of the file name."""
        from src.views.dialogs.visualization_analysis import melting_curve_dialog as m
        path, _ = jwb_file(TEMPS, name='2026_09_21-1-Cell 5.jwb')
        spectra = reader.read_jwb_data(path, selected_channels=[0])
        numbers = [m._NUMBER_RE.findall(s['label']) for s in spectra]
        pos = m.MeltingCurveDialog._pick_varying_number_position(None, numbers)
        assert [float(n[pos]) for n in numbers] == pytest.approx(TEMPS)


class TestImportDialogShowsJwb:

    def _dialog(self, path, monkeypatch):
        from src.views.dialogs.misc import import_dialog as mod
        monkeypatch.setattr(mod, 'ImportProfileManager', MagicMock())
        return mod.ImportDialog(None, [path], {})

    def test_channel_table_and_summary(self, jwb_file, monkeypatch):
        path, _ = jwb_file(TEMPS)
        dlg = self._dialog(path, monkeypatch)
        assert dlg._jws_channels_table.rowCount() == 2
        text = dlg._summary_label.text()
        assert 'temperature scan' in text and '4 temperatures' in text
        assert '10.04' in text and '40.02' in text and 'heating' in text
        assert 'sample-A' in text
        assert dlg._current_jws_selected_channels() == [0, 1]
        assert dlg._padding_row.isHidden()       # spectra are named by temperature, not numbered

    def test_unreadable_file_shows_a_clear_message(self, tmp_path, monkeypatch):
        p = tmp_path / 'junk.jwb'
        p.write_bytes(b'not a JASCO file')
        dlg = self._dialog(str(p), monkeypatch)
        assert 'Could not read JWB file' in dlg._summary_label.text()
