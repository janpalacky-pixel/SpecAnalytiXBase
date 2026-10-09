"""Regression tests for the bugs found during the full sweep of every
spectra-processing operation and analysis/visualization tool for the
"stale cached result survives a dialog reopen" bug class (user request:
"you should check all the spectra processing operations and all spectra
analysis & visualization tools").

Three additional, independent real bugs of this class were found beyond
the earlier Cluster/SOM/QC-Outlier and SVD Background fixes:

  1. SVDBackgroundController.filter_stale_settings -- the settings-cache
     restore (keyed only by selection identity) was putting a stale
     baseline_corrections/inverted_subspectra pick back onto a freshly
     recomputed SVD.
  2. XAxisAlignmentController.show_dialog -- its own preview cache
     (_cached_aligned/_cached_hash) is keyed only on alignment
     PARAMETERS + selection identity, with no awareness that the
     selected spectra's own y-data could have changed (e.g. a baseline
     correction ran) since the preview was computed.
  3. Map2DController.show_dialog -- used plain revision_changed(), which
     doesn't move on a pure selection change with no operation run, so
     switching to a totally different, unrelated selection and reopening
     could redraw the PREVIOUS selection's cached SVD/PCA/NMF/MCR-ALS
     decomposition map as if it belonged to the new one (same bug class
     as Cluster/SOM/QC-Outlier).
  4. PeakFittingController.filter_stale_settings -- the settings-cache
     restore for the same single spectrum was restoring a stale
     fit_results curve and redrawing it over the spectrum's current
     (possibly since-reprocessed) data with no re-fit.
"""

import sys
import types

import numpy as np
import pytest


def _spectrum(label, y, uid=None):
    return {
        'label': label,
        'x_scale': np.array([1.0, 2.0, 3.0]),
        'y_scale': np.array(y, dtype=float),
        'metadata': {'unique_id': uid or f'uid-{label}'},
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
    def __init__(self, revision=0):
        self.view = None
        self.operations_controller = _FakeOperationsController(revision)
        self.selected_spectra = []
        self.original_spectra = []


def _install_fake_dialog(module_path, class_name, get_settings_result=None):
    fake_module = types.ModuleType(module_path)

    class _FakeDialog:
        def __init__(self, *a, **kw):
            self._settings = get_settings_result or {}

        def exec_(self):
            return None

        def get_settings(self):
            return dict(self._settings)

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
# 1. SVD Background -- filter_stale_settings strips computed picks when
#    an operation ran, keeps genuine settings, and passes through
#    untouched when nothing changed.
# --------------------------------------------------------------------- #

def test_svd_background_strips_computed_picks_when_revision_changed():
    from src.controllers.data_analysis.svd_background_controller import (
        SVDBackgroundController)

    mc = _FakeMainController(revision=1)
    ctrl = SVDBackgroundController(mc)

    cached = {
        'correction_mode': 'baseline',
        'max_components': 5,
        'selected_subspectra': [0, 1],
        'baseline_corrections': {'a': [1, 2, 3]},
        'inverted_subspectra': [0],
    }

    # The very first call has no prior revision to compare against, so
    # it conservatively strips too (revision_changed's own "when in
    # doubt, forget" rule) -- seed it here, then assert the real
    # before/after transition below.
    ctrl.filter_stale_settings(dict(cached))

    # An operation ran on the same selection since.
    mc.operations_controller.operations_manager.revision = 2
    out2 = ctrl.filter_stale_settings(dict(cached))
    assert 'baseline_corrections' not in out2
    assert 'inverted_subspectra' not in out2
    # Genuine settings survive.
    assert out2['correction_mode'] == 'baseline'
    assert out2['max_components'] == 5
    assert out2['selected_subspectra'] == [0, 1]


def test_svd_background_keeps_computed_picks_when_revision_unchanged():
    from src.controllers.data_analysis.svd_background_controller import (
        SVDBackgroundController)

    mc = _FakeMainController(revision=1)
    ctrl = SVDBackgroundController(mc)
    cached = {'baseline_corrections': {'a': [1, 2, 3]}, 'inverted_subspectra': [0]}

    ctrl.filter_stale_settings(dict(cached))          # seed _last_seen_revision
    out = ctrl.filter_stale_settings(dict(cached))    # revision still 1
    assert out.get('baseline_corrections') == {'a': [1, 2, 3]}
    assert out.get('inverted_subspectra') == [0]


# --------------------------------------------------------------------- #
# 2. X-axis Alignment -- reopening for the SAME selection after an
#    operation ran must drop the preview cache, not just a changed
#    selection.
# --------------------------------------------------------------------- #

def test_xaxis_alignment_drops_preview_cache_when_revision_changed_same_selection():
    from src.controllers.data_analysis.xaxis_alignment_controller import (
        XAxisAlignmentController)

    _install_fake_dialog(
        'src.views.dialogs.data_analysis.xaxis_alignment_dialog',
        'XAxisAlignmentDialog',
        get_settings_result={
            'reference_spectrum_index': 0, 'max_shift': 10.0,
            'interpolation_method': 'cubic', 'x_range': None,
            '_cached_aligned': ['fake_aligned_result'],
            '_cached_hash': '0|10.0000|cubic|None',
        },
    )

    mc = _FakeMainController(revision=1)
    ctrl = XAxisAlignmentController(mc)
    spectra = [_spectrum('a', [1, 2, 3]), _spectrum('b', [4, 5, 6])]

    settings1 = ctrl.show_dialog(spectra)
    assert settings1['_cached_aligned'] == ['fake_aligned_result']

    # Same exact selection, but an operation ran on it since (e.g. a
    # baseline correction) -- the cached preview no longer matches the
    # data it would be shown against and must not be reused as-is.
    mc.operations_controller.operations_manager.revision = 2
    passed_in = {}
    orig_init = sys.modules[
        'src.views.dialogs.data_analysis.xaxis_alignment_dialog'
    ].XAxisAlignmentDialog.__init__

    def _capture_init(self, *a, **kw):
        passed_in.update(kw.get('current_settings', {}))
        orig_init(self, *a, **kw)

    sys.modules[
        'src.views.dialogs.data_analysis.xaxis_alignment_dialog'
    ].XAxisAlignmentDialog.__init__ = _capture_init

    ctrl.show_dialog(spectra)
    assert '_cached_aligned' not in passed_in
    assert '_cached_hash' not in passed_in
    # Genuine parameters are still carried over.
    assert passed_in.get('max_shift') == 10.0
    assert passed_in.get('interpolation_method') == 'cubic'


def test_xaxis_alignment_keeps_preview_cache_when_nothing_changed():
    from src.controllers.data_analysis.xaxis_alignment_controller import (
        XAxisAlignmentController)

    _install_fake_dialog(
        'src.views.dialogs.data_analysis.xaxis_alignment_dialog',
        'XAxisAlignmentDialog',
        get_settings_result={
            'reference_spectrum_index': 0, 'max_shift': 10.0,
            'interpolation_method': 'cubic', 'x_range': None,
            '_cached_aligned': ['fake_aligned_result'],
            '_cached_hash': '0|10.0000|cubic|None',
        },
    )

    mc = _FakeMainController(revision=1)
    ctrl = XAxisAlignmentController(mc)
    spectra = [_spectrum('a', [1, 2, 3]), _spectrum('b', [4, 5, 6])]

    ctrl.show_dialog(spectra)

    passed_in = {}
    orig_init = sys.modules[
        'src.views.dialogs.data_analysis.xaxis_alignment_dialog'
    ].XAxisAlignmentDialog.__init__

    def _capture_init(self, *a, **kw):
        passed_in.update(kw.get('current_settings', {}))
        orig_init(self, *a, **kw)

    sys.modules[
        'src.views.dialogs.data_analysis.xaxis_alignment_dialog'
    ].XAxisAlignmentDialog.__init__ = _capture_init

    ctrl.show_dialog(spectra)   # same selection, revision unchanged
    assert passed_in.get('_cached_aligned') == ['fake_aligned_result']


# --------------------------------------------------------------------- #
# 3. Map2D -- a pure selection change (no operation run) must still
#    reset the manager, same bug class as Cluster/SOM/QC-Outlier.
# --------------------------------------------------------------------- #

def test_map2d_resets_on_selection_change_alone():
    from src.controllers.visualization_analysis.map2d_controller import (
        Map2DController)

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.map2d_dialog', 'Map2DDialog')

    mc = _FakeMainController(revision=5)
    mc.spectrum_selector = types.SimpleNamespace(
        get_selected_spectra=lambda: mc.selected_spectra)
    ctrl = Map2DController(mc)

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    mc.selected_spectra = [_spectrum('a', [1, 2, 3])]
    ctrl.show_dialog()
    assert len(reset_calls) == 1

    # Completely different, unrelated selection -- no operation ran, so
    # the plain revision counter alone would not have caught this.
    mc.selected_spectra = [_spectrum('b', [4, 5, 6])]
    ctrl.show_dialog()
    assert len(reset_calls) == 2


def test_map2d_keeps_manager_when_nothing_changed():
    from src.controllers.visualization_analysis.map2d_controller import (
        Map2DController)

    _install_fake_dialog(
        'src.views.dialogs.visualization_analysis.map2d_dialog', 'Map2DDialog')

    mc = _FakeMainController(revision=5)
    mc.spectrum_selector = types.SimpleNamespace(
        get_selected_spectra=lambda: mc.selected_spectra)
    ctrl = Map2DController(mc)

    reset_calls = []
    orig_reset = ctrl.manager.reset
    ctrl.manager.reset = lambda: (reset_calls.append(1), orig_reset())

    mc.selected_spectra = [_spectrum('a', [1, 2, 3])]
    ctrl.show_dialog()
    assert len(reset_calls) == 1

    ctrl.show_dialog()   # same selection, same revision
    assert len(reset_calls) == 1


# --------------------------------------------------------------------- #
# 4. Peak Fitting -- reopening on the SAME spectrum after an operation
#    ran must drop the cached fit_results, not just a different spectrum.
# --------------------------------------------------------------------- #

def test_peak_fitting_strips_fit_results_when_revision_changed():
    from src.controllers.data_analysis.peak_fitting_controller import (
        PeakFittingController)

    mc = _FakeMainController(revision=1)
    ctrl = PeakFittingController(mc)

    cached = {
        'fit_results': [{'center': 5.0, 'amplitude': 1.0}],
        'initial_peaks': [{'x': 5.0, 'color': 'red'}],
        'output_options': {'add_fit': True},
    }

    # The very first call has no prior revision to compare against, so
    # it conservatively strips too -- seed it, then assert the real
    # before/after transition below.
    ctrl.filter_stale_settings(dict(cached))

    mc.operations_controller.operations_manager.revision = 2  # an operation ran
    out2 = ctrl.filter_stale_settings(dict(cached))
    assert 'fit_results' not in out2
    # Harmless guesses/settings are kept.
    assert out2['initial_peaks'] == cached['initial_peaks']
    assert out2['output_options'] == cached['output_options']


def test_peak_fitting_keeps_fit_results_when_revision_unchanged():
    from src.controllers.data_analysis.peak_fitting_controller import (
        PeakFittingController)

    mc = _FakeMainController(revision=1)
    ctrl = PeakFittingController(mc)
    cached = {'fit_results': [{'center': 5.0, 'amplitude': 1.0}]}

    ctrl.filter_stale_settings(dict(cached))
    out = ctrl.filter_stale_settings(dict(cached))
    assert out.get('fit_results') == cached['fit_results']


# --------------------------------------------------------------------- #
# 5. Peak Fitting -- a real bug the user hit right after the fix above:
#    fitting peaks, checking an output option (so handle_peak_fitting's
#    own apply_operation() commits and bumps revision), then closing
#    and reopening wiped the very fit_results just saved -- the fit's
#    OWN commit was being mistaken for an unrelated operation that ran
#    on the spectrum meanwhile. _note_own_commit() is what
#    handle_peak_fitting() calls right after its own apply_operation()
#    to fix this; tested directly here since driving the real
#    handle_peak_fitting() needs a full spectra/operations-manager setup
#    well beyond this file's fakes.
# --------------------------------------------------------------------- #

def test_peak_fitting_note_own_commit_prevents_self_invalidation():
    from src.controllers.data_analysis.peak_fitting_controller import (
        PeakFittingController)

    mc = _FakeMainController(revision=1)
    ctrl = PeakFittingController(mc)
    cached = {
        'fit_results': [{'center': 5.0, 'amplitude': 1.0}],
        'output_options': {'add_fit': True},
    }

    # Dialog opens for the first time -- no prior revision, conservative strip.
    ctrl.filter_stale_settings(dict(cached))

    # User fits, checks "add fit", closes: handle_peak_fitting's own
    # apply_operation() bumps revision (simulated directly here)...
    mc.operations_controller.operations_manager.revision = 2
    # ...then calls _note_own_commit() right after, exactly as
    # handle_peak_fitting() now does.
    ctrl._note_own_commit()

    # Reopening now must NOT see that as a stale-triggering change --
    # this is the actual bug: without _note_own_commit, this call would
    # wipe fit_results even though nothing but our own commit happened.
    out = ctrl.filter_stale_settings(dict(cached))
    assert out.get('fit_results') == cached['fit_results']

    # A genuinely later, unrelated operation must still be caught.
    mc.operations_controller.operations_manager.revision = 3
    out2 = ctrl.filter_stale_settings(dict(cached))
    assert 'fit_results' not in out2
