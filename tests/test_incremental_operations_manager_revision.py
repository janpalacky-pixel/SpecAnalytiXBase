# tests/test_incremental_operations_manager_revision.py
#
# IncrementalOperationsManager.revision -- the general "did the spectra
# a dialog is looking at actually change" signal added so a controller
# that keeps ONE persistent manager alive across dialog close/reopen
# (Map2DController, BaselineCorrectionController, ...) can tell "nothing
# happened, restore my cached state" apart from "something changed
# underneath me, drop it" -- see the counter's own docstring in
# IncrementalOperationsManager.__init__ for the full reasoning, and
# Map2DController.show_dialog / BaselineCorrectionController.show_dialog
# for the two current consumers.

import numpy as np
import pytest

from src.modules.data_analysis.incremental_operations_manager import (
    IncrementalOperationsManager,
)


def _spectrum(label, y):
    return {
        'label': label,
        'x_scale': np.arange(len(y), dtype=float),
        'y_scale': np.asarray(y, dtype=float),
        'original_x_scale': np.arange(len(y), dtype=float),
        'original_y_scale': np.asarray(y, dtype=float),
        'metadata': {},
    }


@pytest.fixture
def mgr():
    m = IncrementalOperationsManager()
    m.initialize_with_spectra([_spectrum('a', [1, 2, 3]), _spectrum('b', [4, 5, 6])])
    return m


def test_revision_starts_stable_after_init(mgr):
    r1 = mgr.revision
    r2 = mgr.revision
    assert r1 == r2


def test_apply_operation_bumps_revision(mgr):
    before = mgr.revision
    mgr.apply_operation(
        operation_type='SNIP Baseline', parameters={},
        affected_spectra=[_spectrum('a', [1, 1, 1])])
    assert mgr.revision != before


def test_each_new_operation_bumps_again(mgr):
    mgr.apply_operation(operation_type='op1', parameters={},
                        affected_spectra=[_spectrum('a', [1, 1, 1])])
    r_after_1 = mgr.revision
    mgr.apply_operation(operation_type='op2', parameters={},
                        affected_spectra=[_spectrum('a', [2, 2, 2])])
    assert mgr.revision != r_after_1


def test_set_active_operation_to_different_index_bumps_revision(mgr):
    mgr.apply_operation(operation_type='op1', parameters={},
                        affected_spectra=[_spectrum('a', [1, 1, 1])])
    mgr.apply_operation(operation_type='op2', parameters={},
                        affected_spectra=[_spectrum('a', [2, 2, 2])])
    r_current = mgr.revision

    mgr.set_active_operation(0)   # jump back in history
    assert mgr.revision != r_current


def test_set_active_operation_to_same_index_does_not_bump(mgr):
    mgr.apply_operation(operation_type='op1', parameters={},
                        affected_spectra=[_spectrum('a', [1, 1, 1])])
    r_current = mgr.revision
    # already at this index -- re-selecting it in Operations History
    # should not look like a change
    mgr.set_active_operation(mgr.active_operation_index)
    assert mgr.revision == r_current


def test_returning_to_a_previously_seen_index_still_bumps_revision(mgr):
    """revision is a plain monotonic counter, not a state identifier --
    jumping BACK to an index a dialog had already cached results for
    still counts as "something changed" (a fresh, higher number), it
    does not restore that index's earlier value. Documented as the
    deliberate tradeoff in the counter's own docstring; every current
    caller wants exactly this (always re-check on ANY navigation)."""
    mgr.apply_operation(operation_type='op1', parameters={},
                        affected_spectra=[_spectrum('a', [1, 1, 1])])
    r_at_op1 = mgr.revision
    mgr.apply_operation(operation_type='op2', parameters={},
                        affected_spectra=[_spectrum('a', [2, 2, 2])])

    mgr.set_active_operation(0)   # back to op1's state
    assert mgr.revision != r_at_op1


def test_add_spectra_to_original_bumps_revision_when_spectra_added(mgr):
    before = mgr.revision
    mgr.add_spectra_to_original([_spectrum('c', [7, 8, 9])])
    assert mgr.revision != before


def test_add_spectra_to_original_no_op_does_not_bump(mgr):
    # 'a' already exists -- nothing new actually gets added
    before = mgr.revision
    mgr.add_spectra_to_original([_spectrum('a', [1, 2, 3])])
    assert mgr.revision == before


def test_rename_operation_does_not_bump_revision(mgr):
    """Rename never touches a spectrum's own x_scale/y_scale, only its
    label -- every cache this counter protects is already keyed by
    unique_id specifically so it survives a rename (BaselineManager,
    SpikeRemovalManager, InteractiveSubtractionManager, ...), so treating
    a committed Rename the same as a data-changing operation would throw
    all of that away for no reason. Matches spectrum deletion, which
    isn't even routed through apply_operation() and so never bumps this
    either."""
    before = mgr.revision
    mgr.apply_operation(
        operation_type='Rename', parameters={'renames': {'a': 'a_renamed'}},
        affected_spectra=[_spectrum('a_renamed', [1, 2, 3])])
    assert mgr.revision == before


def test_rename_does_not_mask_a_later_real_operation(mgr):
    """A Rename in between two data-changing operations shouldn't affect
    revision bookkeeping for the operations around it."""
    mgr.apply_operation(operation_type='SNIP Baseline', parameters={},
                        affected_spectra=[_spectrum('a', [1, 1, 1])])
    r_after_snip = mgr.revision

    mgr.apply_operation(operation_type='Rename', parameters={'renames': {'a': 'a2'}},
                        affected_spectra=[_spectrum('a2', [1, 1, 1])])
    assert mgr.revision == r_after_snip   # rename alone: no bump

    mgr.apply_operation(operation_type='Normalization', parameters={},
                        affected_spectra=[_spectrum('a2', [0.5, 0.5, 0.5])])
    assert mgr.revision != r_after_snip   # the next real operation still bumps
