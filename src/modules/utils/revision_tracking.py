"""Shared helper for the "remember unless something changed" pattern used
by every controller that keeps a persistent Manager instance alive across
dialog opens/closes (2D Map, Manual Baseline Correction, NMF, MCR-ALS,
Cluster Analysis, PCA Scores, QC Outlier, SOM, 2D Correlation, ...).

The problem this solves: a dialog's Manager is created once in the
controller's __init__ and reused every time the dialog is reopened, so
whatever it computed/picked last time is still sitting there. Two wrong
ways to handle that:

  - Never reset (the original bug): reopen the dialog after running an
    unrelated operation (e.g. a SNIP baseline correction) and it silently
    shows a fit/selection computed from spectra that no longer exist in
    that form.
  - Always reset (an earlier, blunter fix attempt): reopen the dialog
    having changed nothing at all and it has forgotten everything anyway,
    which is needlessly annoying (NMF/MCR-ALS did this — every re-open
    called manager.reset() unconditionally).

The right behavior is in between: remember the manager's state across a
reopen UNLESS some operation was actually applied (or undo/redo moved to a
different point in history, or new spectra were imported) since the
dialog was last open. `IncrementalOperationsManager.revision` is a plain
monotonically-increasing counter bumped exactly on those events (see its
docstring) — comparing it against the value seen last time this dialog was
shown is sufficient to tell "did anything change" apart from "nothing
changed".

Usage, in a controller that holds a persistent `self.manager`:

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SomeManager()
        self._last_seen_revision = None

    def show_dialog(self, ...):
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
            self.manager.reset()
        ...
"""


def get_current_revision(main_controller):
    """Return the current IncrementalOperationsManager.revision reachable
    from `main_controller`, or None if it can't be found (no
    operations_controller yet, no operations_manager, or an older
    IncrementalOperationsManager without the attribute)."""
    ops_mgr = getattr(
        getattr(main_controller, 'operations_controller', None),
        'operations_manager', None)
    return getattr(ops_mgr, 'revision', None)


def revision_changed(main_controller, last_seen_revision):
    """Compare the current revision against `last_seen_revision`.

    Returns a (should_reset, current_revision) tuple:
      - should_reset is True when the two differ, OR when the current
        revision can't be determined at all — when in doubt, forget
        rather than risk showing stale computed/picked state.
      - current_revision is what the caller should store as its new
        `_last_seen_revision` for next time, regardless of should_reset.
    """
    current_revision = get_current_revision(main_controller)
    should_reset = (current_revision is None or
                    current_revision != last_seen_revision)
    return should_reset, current_revision
