"""tools/help_pictures/keep_unchanged.py: a help picture that differs from the
one before the run only in a few small spots (an icon or colour emoji drawn
with slightly different smoothing) counts as unchanged; a real change does not."""
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


def test_a_few_small_spots_are_the_same_picture(tmp_path):
    ku = _module()

    def bulbs(a):                              # three hint bulbs, 48 px each
        for y in (20, 150, 260):
            a[y:y + 12, 30:34] = 200
    assert ku.nearly_the_same(*_pair(tmp_path, bulbs)) == (True, 144)


def test_a_real_change_is_not(tmp_path):
    ku = _module()

    def text(a):                                # a new line of text: a long spot
        a[100:110, 20:300] = 0
    assert ku.nearly_the_same(*_pair(tmp_path, text))[0] is False

    def many(a):                                # many small changes all over
        for x in range(10, 390, 40):
            a[50:54, x:x + 4] = 0
    assert ku.nearly_the_same(*_pair(tmp_path, many))[0] is False

    def same(a):
        pass
    assert ku.nearly_the_same(*_pair(tmp_path, same)) == (False, 0)
