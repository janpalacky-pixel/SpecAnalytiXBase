"""tools/help_pictures/keep_unchanged.py: a picture that differs only in faint
shades (the smoothing of lines and letters, spread all over the picture)
counts as unchanged; a clear change, even a small one, does not."""
import importlib.util
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'keep_unchanged', os.path.join(ROOT, 'tools', 'help_pictures', 'keep_unchanged.py'))


def _module():
    cwd = os.getcwd()
    try:
        ku = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(ku)          # it changes to the repository folder
        return ku
    finally:
        os.chdir(cwd)


def _pair(tmp_path, change):
    old = np.full((300, 400, 3), 240, dtype=np.uint8)
    new = old.copy()
    change(new)
    paths = []
    for name, a in (('old.png', old), ('new.png', new)):
        Image.fromarray(a).save(tmp_path / name)
        paths.append(str(tmp_path / name))
    return paths


def test_faint_differences_all_over_are_the_same_picture(tmp_path):
    ku = _module()

    def smoothing(a):                         # 100 letters drawn a shade lighter
        for y in range(10, 290, 30):
            for x in range(10, 390, 40):
                a[y:y + 6, x:x + 5] = 225     # 15 per colour = 45 in all
    same, n = ku.nearly_the_same(*_pair(tmp_path, smoothing))
    assert same is True and n == 100 * 30


def test_a_clear_change_is_not_faint(tmp_path):
    ku = _module()

    def many(a):                              # 100 small clear changes
        for y in range(10, 290, 30):
            for x in range(10, 390, 40):
                a[y:y + 6, x:x + 5] = 200     # 40 per colour = 120 in all
    assert ku.nearly_the_same(*_pair(tmp_path, many))[0] is False


def test_faint_differences_and_one_icon_are_the_same_picture(tmp_path):
    ku = _module()

    def smoothing_and_icon(a):
        for y in range(10, 290, 30):
            for x in range(10, 390, 40):
                a[y:y + 6, x:x + 5] = 225     # faint, all over
        a[200:216, 300:316] = 0               # one icon drawn differently
    same, n = ku.nearly_the_same(*_pair(tmp_path, smoothing_and_icon))
    assert same is True and n == 100 * 30 + 256


def test_same_pixels_other_bytes_are_put_back(tmp_path, monkeypatch):
    ku = _module()
    pictures = tmp_path / 'pictures'
    before = tmp_path / 'before'
    pictures.mkdir()
    before.mkdir()
    a = np.full((20, 30, 3), 200, dtype=np.uint8)
    Image.fromarray(a).save(before / 'p.png', compress_level=1)
    Image.fromarray(a).save(pictures / 'p.png', compress_level=9)
    old_bytes = (before / 'p.png').read_bytes()
    assert (pictures / 'p.png').read_bytes() != old_bytes
    monkeypatch.setattr(ku, 'PICTURES', str(pictures))
    ku.main(str(before))
    assert (pictures / 'p.png').read_bytes() == old_bytes
