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
