# tests/test_snapshot.py
#
# Tests for the JSON snapshot save/load round-trip.
# These tests exercise SaveManager._json_encode, _json_decode,
# _to_json, _from_json, and _load_state directly without needing
# a running Qt application.

import pytest
import numpy as np
import json
import os
from src.modules.misc.save_spectra_manager import SaveManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(n_spectra=3, n_points=50):
    """Build a minimal but realistic application state dict."""
    x = np.linspace(100.0, 3500.0, n_points)
    spectra = [
        {
            'label': f'test : {str(i).zfill(4)}',
            'x_scale': np.linspace(100.0, 3500.0, n_points),
            'y_scale': np.random.rand(n_points),
            'metadata': {
                'file_path': 'test.txt',
                'valid_points': n_points,
                'unique_id': f'uid-{i}',
            },
        }
        for i in range(1, n_spectra + 1)
    ]
    return {
        'version': SaveManager.SNAPSHOT_VERSION,
        'timestamp': '2026-05-21T10:00:00',
        'original_spectra': spectra,
        'selected_spectra': spectra[:1],
        'selected_indices': [0],
        'plot_settings': {
            'plot_type': 'Overlay plot',
            'use_automatic_line_colors': True,
            'use_default_points': False,
            'x_scale': 'linear',
            'y_scale': 'linear',
            'grid_settings': {'rows': 1, 'columns': 1},
            'spectra_ordering': 'Alphabetical',
            'reverse_order': False,
        },
        'link_axes': {
            'link_x': False,
            'link_y': False,
            'link_x_direction': 'all',
            'link_y_direction': 'all',
        },
    }


# ---------------------------------------------------------------------------
# Encoder / decoder unit tests
# ---------------------------------------------------------------------------

class TestJsonEncoderDecoder:
    def test_numpy_array_encodes_to_dict(self):
        arr = np.array([1.0, 2.0, 3.0])
        encoded = SaveManager._json_encode(arr)
        assert isinstance(encoded, dict)
        assert encoded['__ndarray__'] is True
        assert 'data' in encoded
        assert 'dtype' in encoded
        assert 'shape' in encoded

    def test_numpy_array_round_trip(self):
        arr = np.array([100.0, 200.0, 300.0], dtype='float64')
        encoded = SaveManager._json_encode(arr)
        decoded = SaveManager._json_decode(encoded)
        assert isinstance(decoded, np.ndarray)
        np.testing.assert_allclose(decoded, arr)

    def test_numpy_integer_scalar(self):
        val = np.int64(42)
        result = SaveManager._json_encode(val)
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float_scalar(self):
        val = np.float64(3.14)
        result = SaveManager._json_encode(val)
        assert abs(result - 3.14) < 1e-10
        assert isinstance(result, float)

    def test_non_ndarray_passes_through_decode(self):
        obj = {'key': 'value', 'number': 42}
        assert SaveManager._json_decode(obj) == obj

    def test_2d_array_shape_preserved(self):
        arr = np.random.rand(10, 5)
        encoded = SaveManager._json_encode(arr)
        decoded = SaveManager._json_decode(encoded)
        assert decoded.shape == (10, 5)
        np.testing.assert_allclose(decoded, arr)

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            SaveManager._json_encode(object())


# ---------------------------------------------------------------------------
# Full JSON serialisation round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_state_serialises_to_string(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        assert isinstance(text, str)
        assert text.startswith('{')

    def test_state_deserialises_from_string(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        assert isinstance(restored, dict)
        assert 'original_spectra' in restored

    def test_numpy_arrays_restored(self):
        state = _make_state(n_spectra=2, n_points=20)
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        for orig, rest in zip(state['original_spectra'],
                               restored['original_spectra']):
            assert isinstance(rest['x_scale'], np.ndarray)
            assert isinstance(rest['y_scale'], np.ndarray)
            np.testing.assert_allclose(rest['x_scale'], orig['x_scale'])
            np.testing.assert_allclose(rest['y_scale'], orig['y_scale'])

    def test_plain_values_preserved(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        assert restored['version'] == SaveManager.SNAPSHOT_VERSION
        assert restored['plot_settings']['plot_type'] == 'Overlay plot'
        assert restored['plot_settings']['use_automatic_line_colors'] is True
        assert restored['selected_indices'] == [0]

    def test_labels_preserved(self):
        state = _make_state(n_spectra=3)
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        orig_labels = [sp['label'] for sp in state['original_spectra']]
        rest_labels = [sp['label'] for sp in restored['original_spectra']]
        assert orig_labels == rest_labels

    def test_metadata_preserved(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        orig_meta = state['original_spectra'][0]['metadata']
        rest_meta = restored['original_spectra'][0]['metadata']
        assert rest_meta['file_path'] == orig_meta['file_path']
        assert rest_meta['valid_points'] == orig_meta['valid_points']


# ---------------------------------------------------------------------------
# File save / load round-trip
# ---------------------------------------------------------------------------

class TestSnapshotFileSaveLoad:
    def test_file_written(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state()
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        assert os.path.exists(tmp_snapx)
        assert os.path.getsize(tmp_snapx) > 0

    def test_file_starts_with_brace(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state()
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        with open(tmp_snapx, 'rb') as f:
            assert f.read(1) == b'{'

    def test_load_state_reads_json(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state(n_spectra=2, n_points=10)
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        loaded = mgr._load_state(tmp_snapx)
        assert 'original_spectra' in loaded
        assert len(loaded['original_spectra']) == 2

    def test_load_state_restores_arrays(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state(n_spectra=1, n_points=20)
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        loaded = mgr._load_state(tmp_snapx)
        x_orig = state['original_spectra'][0]['x_scale']
        x_load = loaded['original_spectra'][0]['x_scale']
        assert isinstance(x_load, np.ndarray)
        np.testing.assert_allclose(x_load, x_orig)

    def test_invalid_file_raises_friendly_error(self, tmp_snapx):
        """Non-JSON file must raise RuntimeError with a clear message."""
        with open(tmp_snapx, 'wb') as f:
            f.write(b'\x80\x04\x95some pickle data')
        mgr = SaveManager()
        with pytest.raises(ValueError, match="not a valid snapshot"):
            mgr._load_state(tmp_snapx)

    def test_excel_file_raises_friendly_error(self, tmp_xlsx):
        """Passing an Excel file as a snapshot must give a clear error."""
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            wb.save(tmp_xlsx)
            mgr = SaveManager()
            with pytest.raises(ValueError, match="not a valid snapshot"):
                mgr._load_state(tmp_xlsx)
        except ImportError:
            pytest.skip("openpyxl not installed")


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

class TestSnapshotPerformance:
    def test_large_snapshot_speed(self, tmp_snapx):
        """1000 spectra × 500 points must save and load in under 3 seconds."""
        import time
        mgr = SaveManager()
        state = _make_state(n_spectra=1000, n_points=500)

        t0 = time.time()
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        save_time = time.time() - t0

        t0 = time.time()
        loaded = mgr._load_state(tmp_snapx)
        load_time = time.time() - t0

        assert save_time < 3.0, f"Save took {save_time:.1f}s"
        assert load_time < 3.0, f"Load took {load_time:.1f}s"
        assert len(loaded['original_spectra']) == 1000
