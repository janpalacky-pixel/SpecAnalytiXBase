# src/modules/utils/correction_history.py

from datetime import datetime


def append_correction_history(original_metadata, operation_name, entry_fields):
    """Append one entry to a spectrum's shared, chronologically-ordered
    correction history.

    Used by every operation that records a per-spectrum correction record
    (SVD Background, Manual Baseline, and any future one that wants this)
    so that applying different operations to the same spectrum over time
    produces ONE combined timeline in the order they actually happened —
    e.g. #1 SVD Background, #2 Manual Baseline, #3 SVD Background again —
    instead of each operation type keeping its own separate history that
    can't be interleaved with the others. Before this, SVD Background and
    Manual Baseline each wrote to their own metadata key
    (svd_correction_history, baseline_correction); a spectrum corrected by
    both, in any order, ended up with two disconnected records that
    couldn't show which one actually happened first, second, third...

    Every entry is tagged with which operation produced it and when, so a
    single flat list correctly represents the real order of events
    regardless of which operations were involved.

    Args:
        original_metadata: the metadata dict of the spectrum BEFORE this
            correction — i.e. read from the INPUT spectrum, not the
            output being built. This is what carries forward whatever
            history already exists from earlier operations, of any type.
        operation_name: short, human-readable operation name, e.g.
            'SVD Background', 'Manual Baseline'.
        entry_fields: dict of this operation's own specific fields for
            this one application (e.g. subspectra used, baseline points
            and fit type). Copied, not mutated.

    Returns:
        A NEW list — the existing history plus one new entry on the end —
        ready to be stored under metadata['correction_history']. Never
        mutates original_metadata or entry_fields in place.
    """
    existing = list((original_metadata or {}).get('correction_history', []))
    entry = dict(entry_fields)
    entry['operation'] = operation_name
    entry['timestamp'] = datetime.now().isoformat()
    return existing + [entry]
