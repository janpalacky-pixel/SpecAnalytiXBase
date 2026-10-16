"""Snapshots also keep (2026-10-16): band markers, plot appearance (axis
titles/fonts, legend, grid lines, layout), Group Statistics groups and
settings, and the processing windows' last settings."""
from types import SimpleNamespace

import numpy as np

from src.modules.misc.save_spectra_manager import SaveManager
from src.modules.visualization.band_marker_manager import BandMarkerManager
from tests.test_snapshot import _FakeMainController, _make_spectra


def _appearance_managers(main):
    for attr, default in (('axis_manager', {'x_label': 'X-axis', 'x_label_font_size': 12}),
                          ('legend_manager', {'visible': False, 'font_size': 10}),
                          ('grid_manager', {'show': False}),
                          ('constrained_layout_manager', {'w_pad': 0.03})):
        setattr(main, attr, SimpleNamespace(default_settings=dict(default),
                                            current_settings=dict(default)))


def _save_and_load(main, target, tmp_path):
    mgr = SaveManager()
    path = tmp_path / 's.snapx'
    mgr.save_snapshot(main, str(path))
    mgr.load_snapshot(target, str(path))
    return mgr


def test_band_markers_round_trip(tmp_path):
    main = _FakeMainController(original_spectra=_make_spectra(2))
    main.band_marker_manager = BandMarkerManager()
    main.band_marker_manager.add(1003.0, label='Phe')
    main.band_marker_manager.add(1450.0, label='CH2')
    target = _FakeMainController(plot_type='Overlay plot')
    target.band_marker_manager = BandMarkerManager()
    _save_and_load(main, target, tmp_path)
    assert [(m['position'], m['label']) for m in target.band_marker_manager.markers] == [
        (1003.0, 'Phe'), (1450.0, 'CH2')]
    # no markers: not written, and loading such a file keeps the current ones
    empty = _FakeMainController(original_spectra=_make_spectra(2))
    empty.band_marker_manager = BandMarkerManager()
    assert 'band_markers' not in SaveManager()._build_state(empty)


def test_plot_appearance_only_changes_are_stored_and_restored(tmp_path):
    main = _FakeMainController(original_spectra=_make_spectra(2))
    _appearance_managers(main)
    assert 'plot_appearance' not in SaveManager()._build_state(main)
    main.axis_manager.current_settings['x_label'] = 'Raman shift / cm-1'
    main.legend_manager.current_settings['visible'] = True
    state = SaveManager()._build_state(main)
    assert set(state['plot_appearance']) == {'axis', 'legend'}
    target = _FakeMainController(plot_type='Overlay plot')
    _appearance_managers(target)
    target.grid_manager.current_settings['show'] = True          # changed before loading
    settings_dict = target.axis_manager.current_settings
    _save_and_load(main, target, tmp_path)
    assert target.axis_manager.current_settings is settings_dict  # in place
    assert target.axis_manager.current_settings['x_label'] == 'Raman shift / cm-1'
    assert target.legend_manager.current_settings['visible'] is True
    assert target.grid_manager.current_settings['show'] is False  # back to its default


def test_group_statistics_groups_and_settings(tmp_path):
    main = _FakeMainController(original_spectra=_make_spectra(2))
    main.group_statistics_controller = SimpleNamespace(
        saved_groups={'s0': 'control', 's1': 'treated'},
        saved_settings={'kind': 'ratio', 'range_a': (1620.0, 1690.0), 'test': 'welch_gh',
                        '_samples': {'s0': 'cell1'}, 'spectra_norm': 'band'})
    target = _FakeMainController(plot_type='Overlay plot')
    groups, settings = {'old': 'x'}, {}
    target.group_statistics_controller = SimpleNamespace(saved_groups=groups,
                                                         saved_settings=settings)
    _save_and_load(main, target, tmp_path)
    assert groups == {'s0': 'control', 's1': 'treated'}            # in place
    assert settings['_samples'] == {'s0': 'cell1'} and settings['test'] == 'welch_gh'
    assert list(settings['range_a']) == [1620.0, 1690.0]


def test_window_settings_of_controllers(tmp_path):
    main = _FakeMainController(original_spectra=_make_spectra(2))
    main.cd_unit_conversion_controller = SimpleNamespace(
        _last_settings={'target_unit': 'delta epsilon', 'path_length': 0.1})
    main.xaxis_alignment_controller = SimpleNamespace(_last_settings={
        'method': 'cross-correlation', '_cached_aligned': [np.zeros(1000)],
        '_cached_reference_key': 'uid-s0'})
    state = SaveManager()._build_state(main)
    assert state['dialog_settings']['xaxis_alignment_controller'] == {
        'method': 'cross-correlation', '_cached_reference_key': 'uid-s0'}   # no cache
    target = _FakeMainController(plot_type='Overlay plot')
    _save_and_load(main, target, tmp_path)
    # missing controllers are created, like the operations do on first use
    assert target.cd_unit_conversion_controller._last_settings['path_length'] == 0.1
    assert type(target.xaxis_alignment_controller).__name__ == 'XAxisAlignmentController'
    assert target.xaxis_alignment_controller._last_settings['method'] == 'cross-correlation'


def test_operations_last_settings_and_selection():
    mgr = SaveManager()
    spectra = _make_spectra(2)
    ratio = {'band_a': (1, 2), 'operation': 'A / B'}
    op = SimpleNamespace(
        operations_manager=SimpleNamespace(operations_chain=[], active_operation_index=-1,
                                           original_spectra=spectra, import_batches=[]),
        current_parameters={'Band Ratio': ratio, 'Normalization': {'mode': 'snv'}},
        last_op_settings={'Band Ratio': dict(ratio), 'Peak Fitting': {'model': 'Voigt'}},
        last_selection_hash='s0,s1')
    main = _FakeMainController(original_spectra=spectra)
    main.operations_controller = op
    ops = mgr._build_state(main)['operations']
    assert ops['last_op_settings_same'] == ['Band Ratio']          # not stored twice
    assert ops['last_op_settings'] == {'Peak Fitting': {'model': 'Voigt'}}
    assert ops['last_selection_hash'] == 's0,s1'
    target_op = SimpleNamespace(
        operations_manager=SimpleNamespace(operations_chain=[], active_operation_index=-1,
                                           original_spectra=[], import_batches=[]),
        current_parameters={}, last_op_settings={}, last_selection_hash=None)
    target = _FakeMainController(original_spectra=spectra)
    target.operations_controller = target_op
    mgr._restore_operations(target, ops)
    assert target_op.last_op_settings == {'Band Ratio': ratio, 'Peak Fitting': {'model': 'Voigt'}}
    assert target_op.last_selection_hash == 's0,s1'
