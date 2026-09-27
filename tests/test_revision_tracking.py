"""Tests for the shared revision_tracking helper used by every
controller that keeps a persistent Manager alive across dialog
reopens (2D Map, Manual Baseline Correction, NMF, MCR-ALS, ...).
"""

from src.modules.utils.revision_tracking import (
    get_current_revision,
    revision_changed,
)


class _FakeOpsManager:
    def __init__(self, revision):
        self.revision = revision


class _FakeOpsController:
    def __init__(self, revision):
        self.operations_manager = _FakeOpsManager(revision)


class _FakeMainController:
    def __init__(self, revision=None, has_operations_controller=True):
        if has_operations_controller:
            self.operations_controller = _FakeOpsController(revision)


def test_get_current_revision_reads_through_the_chain():
    mc = _FakeMainController(revision=5)
    assert get_current_revision(mc) == 5


def test_get_current_revision_none_when_no_operations_controller():
    mc = _FakeMainController(has_operations_controller=False)
    assert get_current_revision(mc) is None


def test_get_current_revision_none_when_no_operations_manager():
    class MC:
        pass
    mc = MC()
    mc.operations_controller = object()  # no operations_manager attr
    assert get_current_revision(mc) is None


def test_revision_changed_false_when_unchanged():
    mc = _FakeMainController(revision=3)
    should_reset, current = revision_changed(mc, last_seen_revision=3)
    assert should_reset is False
    assert current == 3


def test_revision_changed_true_when_moved():
    mc = _FakeMainController(revision=4)
    should_reset, current = revision_changed(mc, last_seen_revision=3)
    assert should_reset is True
    assert current == 4


def test_revision_changed_true_on_first_call_with_none_last_seen():
    # A controller's _last_seen_revision starts as None; the very first
    # show_dialog() call should reset (nothing trustworthy seen yet)
    # unless the current revision also happens to be None.
    mc = _FakeMainController(revision=0)
    should_reset, current = revision_changed(mc, last_seen_revision=None)
    assert should_reset is True
    assert current == 0


def test_revision_changed_true_when_current_revision_unavailable():
    # When in doubt (no operations_controller reachable at all), forget
    # rather than risk showing stale computed/picked state.
    mc = _FakeMainController(has_operations_controller=False)
    should_reset, current = revision_changed(mc, last_seen_revision=None)
    assert should_reset is True
    assert current is None


# --------------------------------------------------------------------- #
# selection_hash / selection_or_revision_changed -- for controllers whose
# Manager caches ONE result computed from the WHOLE selection at once
# (Cluster Analysis, SOM, QC/Outlier), read directly by the dialog with
# no per-spectrum scoping. revision_changed alone is not enough here:
# switching to a different, unrelated selection does not bump revision
# at all (no operation ran), so a stale result from the OLD selection
# would still pass an unchanged-revision check. Bug found in practice
# while re-checking this mechanism against the actual dialogs.
# --------------------------------------------------------------------- #

from src.modules.utils.revision_tracking import (
    selection_hash,
    selection_or_revision_changed,
)


def _spec(label, uid=None):
    return {'label': label, 'metadata': {'unique_id': uid or f'uid-{label}'}}


def test_selection_hash_same_set_same_hash_regardless_of_order():
    a = [_spec('x'), _spec('y')]
    b = [_spec('y'), _spec('x')]
    assert selection_hash(a) == selection_hash(b)


def test_selection_hash_different_set_different_hash():
    a = [_spec('x'), _spec('y')]
    b = [_spec('x'), _spec('z')]
    assert selection_hash(a) != selection_hash(b)


def test_selection_hash_empty_is_none():
    assert selection_hash([]) is None
    assert selection_hash(None) is None


def test_selection_or_revision_changed_resets_on_selection_change_alone():
    """The actual bug: revision unchanged (no operation ran), but the
    selection is a completely different, unrelated set of spectra --
    must still report should_reset=True."""
    mc = _FakeMainController(revision=5)
    spectra_a = [_spec('a'), _spec('b')]
    spectra_b = [_spec('c'), _spec('d')]

    should_reset, hash_a, rev = selection_or_revision_changed(
        mc, spectra_a, last_selection_hash=None, last_seen_revision=None)
    assert should_reset is True   # first call, nothing trusted yet

    should_reset, hash_b, rev = selection_or_revision_changed(
        mc, spectra_b, last_selection_hash=hash_a, last_seen_revision=rev)
    assert should_reset is True   # different selection, same revision


def test_selection_or_revision_changed_keeps_state_when_neither_changed():
    mc = _FakeMainController(revision=5)
    spectra = [_spec('a'), _spec('b')]

    _, h, r = selection_or_revision_changed(
        mc, spectra, last_selection_hash=None, last_seen_revision=None)
    should_reset, h2, r2 = selection_or_revision_changed(
        mc, spectra, last_selection_hash=h, last_seen_revision=r)
    assert should_reset is False


def test_selection_or_revision_changed_resets_on_revision_change_alone():
    mc = _FakeMainController(revision=1)
    spectra = [_spec('a'), _spec('b')]

    _, h, r = selection_or_revision_changed(
        mc, spectra, last_selection_hash=None, last_seen_revision=None)
    mc.operations_controller.operations_manager.revision = 2   # an operation ran
    should_reset, h2, r2 = selection_or_revision_changed(
        mc, spectra, last_selection_hash=h, last_seen_revision=r)
    assert should_reset is True
