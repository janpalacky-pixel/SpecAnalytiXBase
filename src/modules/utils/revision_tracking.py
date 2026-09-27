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

Usage, in a controller whose Manager caches state keyed PER SPECTRUM by
stable identity (BaselineManager's baseline points, SpikeRemovalManager's
detected spikes, InteractiveSubtractionManager's stored factors, ...) —
revision alone is enough, since each spectrum's own entry is only ever
looked up under its own key regardless of what else happens to be
selected:

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SomeManager()
        self._last_seen_revision = None

    def show_dialog(self, ...):
        should_reset, self._last_seen_revision = revision_changed(
            self.controller, self._last_seen_revision)
        if should_reset:
            self.manager.reset()   # or a scoped, per-spectrum clear
        ...

A DIFFERENT situation, and a real bug found in practice: a controller
whose Manager caches ONE result computed from the WHOLE selection at
once (Cluster Analysis's cluster_labels, SOM's hit_map, QC/Outlier's t2,
...), where the dialog reads that cached result directly — gated only on
"is it None", with no way to tell whether it was computed from the
CURRENT selection or a completely different, unrelated one — the moment
the user does anything that reads it (e.g. switching the visualization
mode combo) BEFORE ever clicking Run/Compute for this session. Revision
alone does not protect this: selecting a different, unrelated set of
spectra does not bump revision at all (no operation ran), so a stale
result from the OLD selection would still be shown. These controllers
need `selection_or_revision_changed` instead, which also resets on a
plain selection change:

    def __init__(self, main_controller):
        self.controller = main_controller
        self.manager = SomeManager()
        self._last_seen_revision = None
        self._last_selection_hash = None

    def show_dialog(self, selected_spectra, ...):
        should_reset, self._last_selection_hash, self._last_seen_revision = \
            selection_or_revision_changed(
                self.controller, selected_spectra,
                self._last_selection_hash, self._last_seen_revision)
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


def selection_hash(spectra):
    """Order-independent identity hash of a set of spectra, for
    detecting whether "the selection" is the same set as last time --
    see spectrum_identity.spectrum_key for what identifies one spectrum.
    None for an empty/falsy selection, distinguishable from any real
    selection's hash."""
    if not spectra:
        return None
    from src.modules.utils.spectrum_identity import spectrum_key
    return ','.join(sorted(spectrum_key(s) for s in spectra))


def selection_or_revision_changed(main_controller, selected_spectra,
                                  last_selection_hash, last_seen_revision):
    """Like revision_changed, but ALSO resets when the selection itself
    changed -- for a controller whose Manager caches one result computed
    from the whole current selection at once, read directly by the
    dialog with no per-spectrum scoping to fall back on (see this
    module's docstring for the concrete bug this fixes).

    Returns (should_reset, current_selection_hash, current_revision) --
    the caller stores both of the latter as its new
    `_last_selection_hash`/`_last_seen_revision` regardless of
    should_reset.
    """
    current_hash = selection_hash(selected_spectra)
    revision_should_reset, current_revision = revision_changed(
        main_controller, last_seen_revision)
    should_reset = revision_should_reset or current_hash != last_selection_hash
    return should_reset, current_hash, current_revision
