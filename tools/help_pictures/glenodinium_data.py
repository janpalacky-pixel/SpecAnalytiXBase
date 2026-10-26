"""The Glenodinium map for the Unmixing pictures of the 2D Map help: 21 000
processed spectra (ALS baseline, cosmic rays removed). They come from a
snapshot that is not in git (about 270 MB): the file named by the
environment variable SAX_GLENODINIUM, else
dev_notes/glenodium_map_17_10_2026.snapx. Read once and then kept as
tools/help_pictures/cache/glenodinium.npz (not in git either), which loads
in seconds. Without both, load() returns None and those pictures are
skipped (they change only when Unmixing changes)."""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cache', 'glenodinium.npz')
SNAPSHOT = os.environ.get('SAX_GLENODINIUM') or os.path.join(
    'dev_notes', 'glenodium_map_17_10_2026.snapx')


def load():
    """{'Y', 'x', 'labels', 'uids', 'meta'} or None."""
    if not os.path.isfile(CACHE):
        if not os.path.isfile(SNAPSHOT):
            return None
        from src.modules.misc import snapshot_format
        spectra = snapshot_format.read(SNAPSHOT)['original_spectra']
        meta = dict(spectra[0].get('metadata') or {})
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        np.savez(CACHE,
                 Y=np.array([s['y_scale'] for s in spectra], dtype=np.float32),
                 x=np.asarray(spectra[0]['x_scale'], dtype=float),
                 labels=np.array([s['label'] for s in spectra]),
                 uids=np.array([(s.get('metadata') or {}).get('unique_id', '') for s in spectra]),
                 meta=json.dumps(meta, default=str))
    data = np.load(CACHE)
    return {'Y': data['Y'], 'x': data['x'], 'labels': data['labels'], 'uids': data['uids'],
            'meta': json.loads(str(data['meta']))}
