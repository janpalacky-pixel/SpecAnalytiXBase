"""Snapshot format version 2 (snapshot_format.py): binary arrays, each
distinct array once, lossless 32-bit storage, old files still readable."""
import gzip
import json
import os
import zipfile

import numpy as np
import pytest

from src.modules.misc import snapshot_format as sf
from src.modules.misc.save_spectra_manager import SaveManager


def _state(n=50, points=400, seed=0):
    rng = np.random.default_rng(seed)
    x = np.linspace(200, 3800, points)
    raw = [rng.integers(0, 4000, points).astype(np.float64) for _ in range(n)]     # 32-bit exact
    processed = [y - 0.123456789 * np.arange(points) for y in raw]                  # full 64-bit
    original = [{'label': f's{i}', 'x_scale': x.copy(), 'y_scale': raw[i], 'metadata': {'k': i}}
                for i in range(n)]
    after = [dict(s, y_scale=processed[i]) for i, s in enumerate(original)]
    return {'timestamp': 't', 'original_spectra': after,
            'operations': {'operations_chain': [{'type': 'Automated Baseline', 'output_spectra': after}],
                           'original_spectra': original},
            'scalars': [np.float64(1.5), np.int64(3)],
            'odd': {'empty': np.zeros(0), 'matrix': np.arange(6.0).reshape(2, 3),
                    'ints': np.arange(5), 'nan': np.array([1.0, np.nan]),
                    'strings': np.array(['a', 'b'])}}


def test_round_trip_is_exact(tmp_path):
    state = _state()
    path = str(tmp_path / 's.snapx')
    sf.write(state, path)
    back = sf.read(path)
    for a, b in zip(back['original_spectra'], state['original_spectra']):
        assert a['label'] == b['label'] and a['metadata'] == b['metadata']
        assert a['y_scale'].dtype == np.float64
        assert np.array_equal(a['y_scale'], b['y_scale'])                 # bit-identical
        assert np.array_equal(a['x_scale'], b['x_scale'])
    for a, b in zip(back['operations']['original_spectra'], state['operations']['original_spectra']):
        assert np.array_equal(a['y_scale'], b['y_scale'])
    odd = back['odd']
    assert odd['empty'].shape == (0,) and odd['matrix'].shape == (2, 3)
    assert odd['ints'].dtype == state['odd']['ints'].dtype
    assert np.array_equal(odd['nan'], state['odd']['nan'], equal_nan=True)
    assert odd['strings'] == ['a', 'b']
    assert back['scalars'] == [1.5, 3]
    assert sf.read(sf.to_bytes({'flag': np.bool_(True)}))['flag'] is True
    assert not back['original_spectra'][0]['y_scale'].flags.writeable    # read-only, as before


def test_each_distinct_array_is_stored_once_and_32_bit_when_lossless(tmp_path):
    state = _state(n=50, points=400)
    path = str(tmp_path / 's.snapx')
    sf.write(state, path)
    with zipfile.ZipFile(path) as z:
        entries = json.loads(z.read('arrays.json'))['arrays']
    spectra_arrays = [e for e in entries if e['shape'] == [400]]
    # 50 raw + 50 processed + 1 shared x axis (the 50 copies are identical)
    assert len(spectra_arrays) == 101
    assert sum(e['stored'] == '<f4' for e in spectra_arrays) == 50          # raw counts: 32-bit exact
    assert sum(e['stored'] == '<f8' for e in spectra_arrays) == 51          # processed + the x axis


def test_much_smaller_than_version_1(tmp_path):
    state = _state(n=200, points=800)
    v1 = len(gzip.compress(SaveManager._to_json(state).encode('utf-8'), 6))
    v2 = sf.write(state, str(tmp_path / 's.snapx'), 6)
    assert v2 < v1 / 2      # (~5x on a real Raman map, see snapshot_format.py)


def test_save_manager_reads_both_versions(tmp_path):
    state = _state(n=5, points=50)
    mgr = SaveManager()
    v1 = tmp_path / 'old.snapx'
    v1.write_bytes(gzip.compress(SaveManager._to_json(state).encode('utf-8')))
    v2 = tmp_path / 'new.snapx'
    sf.write(state, str(v2))
    for path in (v1, v2):
        loaded = mgr._load_state(str(path))
        assert np.array_equal(loaded['original_spectra'][2]['y_scale'],
                              state['original_spectra'][2]['y_scale'])


def test_damaged_and_newer_files_give_clear_errors(tmp_path):
    mgr = SaveManager()
    good = tmp_path / 'good.snapx'
    sf.write(_state(n=3, points=20), str(good))
    damaged = tmp_path / 'damaged.snapx'
    damaged.write_bytes(good.read_bytes()[:200])
    with pytest.raises(ValueError, match='not a valid snapshot'):
        mgr._load_state(str(damaged))
    newer = tmp_path / 'newer.snapx'
    with zipfile.ZipFile(newer, 'w') as z:
        z.writestr('format.json', json.dumps({'format': sf.FORMAT_NAME, 'version': 99}))
        z.writestr('arrays.json', '{"arrays": []}')
        z.writestr('arrays.bin', b'')
        z.writestr('state.json', '{}')
    with pytest.raises(ValueError, match='newer version'):
        mgr._load_state(str(newer))


def test_write_is_atomic_and_can_be_aborted(tmp_path):
    path = tmp_path / 's.snapx'
    path.write_bytes(b'previous content')
    with pytest.raises(sf.Aborted):
        sf.write(_state(n=5, points=20), str(path), abort=lambda: True)
    assert path.read_bytes() == b'previous content'                   # untouched
    assert [p.name for p in tmp_path.iterdir()] == ['s.snapx']         # no temporary file left
