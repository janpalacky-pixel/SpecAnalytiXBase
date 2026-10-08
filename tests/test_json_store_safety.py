"""Saved presets / import profiles / pipelines must never be lost silently.

Before: an unreadable file (e.g. half-written by a crash during a save) was
treated as "nothing saved"; the next save then wrote a file containing only
the new item and every earlier one was gone. And a save emptied the file
before writing it, so an interrupted save could produce such a file.
"""
import os

import pytest

import src.modules.data_analysis.normalization_manager as nm_module
import src.modules.utils.json_store as json_store
from src.modules.data_analysis.normalization_manager import NormalizationManager
from src.modules.misc.import_profile_manager import ImportProfileManager
from src.modules.misc.pipeline_manager import PipelineManager
from src.modules.utils.json_store import read_json_store, write_json_atomic


def _backups(folder):
    return sorted(f for f in os.listdir(folder) if '.corrupt-' in f)


# ------------------------------------------------------------ helper itself

def test_missing_file_is_simply_empty(tmp_path):
    assert read_json_store(str(tmp_path / 'nothing.json'), 'things') == {}
    assert _backups(tmp_path) == []


def test_round_trip(tmp_path):
    path = str(tmp_path / 'store.json')
    write_json_atomic(path, {'a': [1, 2], 'b': {'c': 'é'}})
    assert read_json_store(path, 'things') == {'a': [1, 2], 'b': {'c': 'é'}}


@pytest.mark.parametrize('content', ['{"half-writ', '', '[1, 2, 3]', '\x00\x00garbage'])
def test_unreadable_file_is_kept_aside_before_being_treated_as_empty(tmp_path, content):
    path = tmp_path / 'store.json'
    path.write_text(content, encoding='utf-8')
    assert read_json_store(str(path), 'things') == {}
    backups = _backups(tmp_path)
    assert len(backups) == 1
    assert (tmp_path / backups[0]).read_text(encoding='utf-8') == content


def test_two_damaged_reads_in_the_same_second_keep_two_copies(tmp_path):
    path = tmp_path / 'store.json'
    path.write_text('{broken', encoding='utf-8')
    read_json_store(str(path), 'things')
    read_json_store(str(path), 'things')
    assert len(_backups(tmp_path)) == 2


def test_interrupted_save_leaves_the_old_file_complete(tmp_path, monkeypatch):
    path = str(tmp_path / 'store.json')
    write_json_atomic(path, {'old': 1})

    def crash(*args, **kwargs):
        raise OSError('disk full (simulated)')
    monkeypatch.setattr(json_store.json, 'dump', crash)
    with pytest.raises(OSError):
        write_json_atomic(path, {'new': 2})
    monkeypatch.undo()
    assert read_json_store(path, 'things') == {'old': 1}
    assert [f for f in os.listdir(tmp_path) if f.startswith('.tmp-')] == []   # no temp leftovers


# ------------------------------------------------------------ the three stores

def test_normalization_presets_survive_a_damaged_file(tmp_path, monkeypatch):
    path = tmp_path / 'normalization_region_presets.json'
    monkeypatch.setattr(nm_module, '_PRESETS_FILE', str(path))
    NormalizationManager.save_region_preset('Amide I', [(1600, 1700)])
    NormalizationManager.save_region_preset('CH', [(2800, 3000)])
    good = path.read_text(encoding='utf-8')

    path.write_text(good[: len(good) // 2], encoding='utf-8')     # damaged mid-file
    NormalizationManager.save_region_preset('New', [(100, 200)])  # the old data-loss moment

    backups = _backups(tmp_path)
    assert len(backups) == 1
    kept = (tmp_path / backups[0]).read_text(encoding='utf-8')
    assert kept == good[: len(good) // 2]                         # exactly what was on disk
    assert 'Amide I' in kept                                      # so it can be recovered by hand
    assert NormalizationManager.list_region_presets() == {'New': [(100, 200)]}


def test_normalization_presets_round_trip_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(nm_module, '_PRESETS_FILE', str(tmp_path / 'p.json'))
    NormalizationManager.save_region_preset('A', [(1, 2), (3, 4)])
    assert NormalizationManager.list_region_presets() == {'A': [(1, 2), (3, 4)]}
    NormalizationManager.delete_region_preset('A')
    assert NormalizationManager.list_region_presets() == {}


@pytest.mark.parametrize('make, save, names', [
    (ImportProfileManager, lambda m, n: m.save_profile(n, {'delimiter': ','}), lambda m: m.list_profiles()),
    (PipelineManager, lambda m, n: m.save_pipeline(n, [{'operation': 'x'}]), lambda m: m.list_pipelines()),
])
def test_profiles_and_pipelines_keep_a_damaged_file(tmp_path, make, save, names):
    m = make()
    m._path = str(tmp_path / 'store.json')
    save(m, 'first'); save(m, 'second')
    assert names(m) == ['first', 'second']
    with open(m._path, 'a', encoding='utf-8') as fh:
        fh.write('}}} damage')
    save(m, 'third')
    assert names(m) == ['third']
    backups = _backups(tmp_path)
    assert len(backups) == 1
    assert 'first' in (tmp_path / backups[0]).read_text(encoding='utf-8')
