"""Behavioral tests for the "remember unless something changed" fix
applied to every controller that keeps a persistent Manager alive across
dialog reopens.

Each dialog's real Qt widget is swapped out for a lightweight stub (via
sys.modules, matching the controller's own local `from ... import
XDialog` inside show_dialog/show_interactive_dialog) so these run
without a QApplication, and assert directly on whether
manager.reset()/manager state was cleared -- the actual behavior the
user reported and asked to have fixed everywhere, not just the revision
counter's own bookkeeping (already covered by
test_incremental_operations_manager_revision.py) or the shared helper in
isolation (test_revision_tracking.py).
"""

import sys
import types

import numpy as np
import pytest


def _spectrum(label, y):
    return {
        'label': label,
        'x_scale': np.array([1.0, 2.0, 3.0]),
        'y_scale': np.array(y, dtype=float),
        'metadata': {'unique_id': f'uid-{label}'},
    }


class _FakeOpsManager:
    def __init__(self, revision=0):
        self.revision = revision


class _FakeOperationsController:
    def __init__(self, revision=0):
        self.operations_manager = _FakeOpsManager(revision)
        self.last_op_settings = {}
        self.current_parameters = {}


class _FakeMainController:
    """Bare-bones stand-in for the real main_controller -- just enough
    surface for the controllers under test."""
    def __init__(self, revision=0):
        self.view = None
        self.operations_controller = _FakeOperationsController(revision)
        self.selected_spectra = []
        self.original_spectra = []


def _install_fake_dialog(module_path, class_name, **extra_attrs):
    """Register a fake module at `module_path` (e.g.
    'src.views.dialogs.visualization_analysis.nmf_dialog') exposing a
    do-nothing `class_name` Dialog, so the controller's own local
    `from module_path import class_name` picks up this stub via
    sys.modules instead of constructing a real Qt widget."""
    fake_module = types.ModuleType(module_path)

    class _FakeDialog:
        def __init__(self, *a, **kw):
            pass

        def exec_(self):
            return None

    for k, v in extra_attrs.items():
        setattr(_FakeDialog, k, v)

    setattr(fake_module, class_name, _FakeDialog)
    sys.modules[module_path] = fake_module
    return fake_module


@pytest.fixture(autouse=True)
def _restore_real_dialog_modules():
    """Put the real dialog modules back after each test.

    _install_fake_dialog() replaces entries in sys.modules. Leaving those
    stubs behind used to be harmless, until tests/test_smoke_all_tools.py
    -- which opens the REAL NMF / MCR-ALS / ... dialogs later in the same
    run -- picked up a leftover `_FakeDialog` instead."""
    saved = dict(sys.modules)
    yield
    for name, module in list(sys.modules.items()):
        if saved.get(name) is module:
            continue
        if isinstance(module, types.ModuleType) and getattr(module, '__file__', None) is None \
                and name.startswith('src.'):
            if name in saved:
                sys.modules[name] = saved[name]
            else:
                del sys.modules[name]


# --------------------------------------------------------------------- #
# NMF / MCR-ALS -- explicit user request: "the standalone NMF/MCR-ALS
# dialogs currently do the opposite of what you want" -> fix it.
# --------------------------------------------------------------------- #

def test_nmf_controller_keeps_manager_when_revision_unchanged():
    from src.controllers.visualization_analysis.nmf_controller import NMFController

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.nmf_dialog', 'NMFDialog')

    mc = _FakeMainController(revision=7)
    ctrl = NMFController(mc)
    spectra = [_spectrum('a', [1, 2, 3])]

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    ctrl.show_dialog(spectra)   # first open: nothing seen yet -> resets
    assert len(reset_calls) == 1

    ctrl.show_dialog(spectra)   # reopen, revision unchanged -> keeps state
    assert len(reset_calls) == 1


def test_nmf_controller_resets_manager_when_revision_changed():
    from src.controllers.visualization_analysis.nmf_controller import NMFController

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.nmf_dialog', 'NMFDialog')

    mc = _FakeMainController(revision=1)
    ctrl = NMFController(mc)
    spectra = [_spectrum('a', [1, 2, 3])]

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    ctrl.show_dialog(spectra)
    assert len(reset_calls) == 1

    mc.operations_controller.operations_manager.revision = 2  # an operation ran
    ctrl.show_dialog(spectra)
    assert len(reset_calls) == 2


def test_mcr_als_controller_keeps_manager_when_revision_unchanged():
    from src.controllers.visualization_analysis.mcr_als_controller import MCRALSController

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.mcr_als_dialog', 'MCRALSDialog')

    mc = _FakeMainController(revision=3)
    ctrl = MCRALSController(mc)
    spectra = [_spectrum('a', [1, 2, 3])]

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    ctrl.show_dialog(spectra)
    assert len(reset_calls) == 1
    ctrl.show_dialog(spectra)
    assert len(reset_calls) == 1


def test_mcr_als_controller_resets_manager_when_revision_changed():
    from src.controllers.visualization_analysis.mcr_als_controller import MCRALSController

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.mcr_als_dialog', 'MCRALSDialog')

    mc = _FakeMainController(revision=5)
    ctrl = MCRALSController(mc)
    spectra = [_spectrum('a', [1, 2, 3])]

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    ctrl.show_dialog(spectra)
    assert len(reset_calls) == 1

    mc.operations_controller.operations_manager.revision = 6
    ctrl.show_dialog(spectra)
    assert len(reset_calls) == 2


# --------------------------------------------------------------------- #
# QCOutlierController -- this one previously had the OPPOSITE bug (never
# reset at all), unlike NMF/MCR-ALS's "always reset". Verify it now
# forgets on a real change and remembers otherwise.
# --------------------------------------------------------------------- #

def test_qc_outlier_controller_resets_only_when_revision_changed():
    from src.controllers.visualization_analysis.qc_outlier_controller import QCOutlierController

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.qc_outlier_dialog', 'QCOutlierDialog')

    mc = _FakeMainController(revision=0)
    mc.selected_spectra = [_spectrum(f's{i}', [1, 2, 3]) for i in range(5)]
    ctrl = QCOutlierController(mc)

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    ctrl.run_qc_outlier_analysis()
    assert len(reset_calls) == 1

    ctrl.run_qc_outlier_analysis()   # nothing changed -> still remembers
    assert len(reset_calls) == 1

    mc.operations_controller.operations_manager.revision = 1
    ctrl.run_qc_outlier_analysis()   # an operation ran -> forgets
    assert len(reset_calls) == 2


def test_qc_outlier_controller_resets_on_selection_change_alone():
    """QCOutlierManager.t2/q etc. are computed from the WHOLE selection
    at once and read directly by the dialog with no per-spectrum
    scoping (unlike Baseline/SpikeRemoval/InteractiveSubtraction) --
    switching to a different, unrelated selection with NO operation
    applied must still reset, or a stale result from the old selection
    could be shown before anything is (re-)computed for the new one."""
    from src.controllers.visualization_analysis.qc_outlier_controller import QCOutlierController

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.qc_outlier_dialog', 'QCOutlierDialog')

    mc = _FakeMainController(revision=0)
    mc.selected_spectra = [_spectrum(f's{i}', [1, 2, 3]) for i in range(5)]
    ctrl = QCOutlierController(mc)

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    ctrl.run_qc_outlier_analysis()
    assert len(reset_calls) == 1

    # switch to a totally different, unrelated selection -- revision is
    # STILL 0 (no operation ran), but this must still reset
    mc.selected_spectra = [_spectrum(f't{i}', [4, 5, 6]) for i in range(5)]
    ctrl.run_qc_outlier_analysis()
    assert len(reset_calls) == 2

    # reopening for that SAME new selection, still nothing changed ->
    # remembers again
    ctrl.run_qc_outlier_analysis()
    assert len(reset_calls) == 2
