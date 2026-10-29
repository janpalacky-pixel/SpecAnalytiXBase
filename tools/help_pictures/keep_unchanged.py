"""After a run: a picture that differs from the one before the run only in a
few pixels of a few small spots (a system icon or a colour emoji such as the
light bulb of the hints, drawn with slightly different smoothing - Windows
does that now and then) - besides faint shades all over (the smoothing of
lines and letters), which do not count - or not at all (only the file bytes
differ) is put back as it was, so git
lists only pictures that really changed. make_all_help_pictures.bat copies the
pictures to tools/logs/pictures_before/ before the run and calls this after
it; it prints what it put back:
    python tools/help_pictures/keep_unchanged.py tools/logs/pictures_before"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)

import numpy as np
from PIL import Image

PICTURES = os.path.join('resources', 'images', 'help_screenshots')
MAX_PIXELS = 400          # at most this many pixels differ in each spot ...
MAX_SPOT = 48             # ... each spot within a square of this size (an icon)
MAX_SPOTS = 6             # ... and at most this many spots
FAINT = 60                # pixels differing by at most this (red+green+blue) are only
                          # smoothing and are not counted; a real change (text, a line,
                          # a colour) differs far more


def nearly_the_same(old_path, new_path):
    """(True/False, number of differing pixels)."""
    old = np.asarray(Image.open(old_path).convert('RGB')).astype(int)
    new = np.asarray(Image.open(new_path).convert('RGB')).astype(int)
    if old.shape != new.shape:
        return False, -1
    strength = np.abs(old - new).sum(axis=2)
    count = int((strength > 0).sum())
    if count == 0:
        return False, 0                       # identical: nothing to do
    diff = strength > FAINT                   # faint smoothing differences do not count
    if not diff.any():
        return True, count
    from scipy import ndimage
    # clearly differing pixels closer than a few pixels belong to one spot
    spots, n = ndimage.label(ndimage.binary_dilation(diff, iterations=3))
    if n > MAX_SPOTS:
        return False, count
    for k, box in enumerate(ndimage.find_objects(spots), start=1):
        inside = diff[box] & (spots[box] == k)
        ys, xs = np.nonzero(inside)
        size = max(xs.max() - xs.min(), ys.max() - ys.min()) + 1
        if size > MAX_SPOT or inside.sum() > MAX_PIXELS:
            return False, count
    return True, count


def main(before):
    kept = 0
    for folder, _, files in os.walk(PICTURES):
        for name in files:
            if not name.lower().endswith('.png'):
                continue
            new_path = os.path.join(folder, name)
            old_path = os.path.join(before, os.path.relpath(new_path, PICTURES))
            if not os.path.isfile(old_path):
                continue
            with open(old_path, 'rb') as fh:
                old_bytes = fh.read()
            with open(new_path, 'rb') as fh:
                if fh.read() == old_bytes:
                    continue
            same, n = nearly_the_same(old_path, new_path)
            if same or n == 0:                # n == 0: the same pixels, other bytes
                with open(new_path, 'wb') as fh:
                    fh.write(old_bytes)
                kept += 1
                print(f'kept as it was (only {n} pixels differed): {new_path}')
    print(f'{kept} picture(s) kept as they were.')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join('tools', 'logs', 'pictures_before'))
