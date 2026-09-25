# tests/test_snapshot.py
#
# Tests for the JSON snapshot save/load round-trip.
# These tests exercise SaveManager._json_encode, _json_decode,
# _to_json, _from_json, and _load_state directly without needing
# a running Qt application.

import pytest
import numpy as np
import json
import os
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from src.modules.misc.save_spectra_manager import SaveManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(n_spectra=3, n_points=50):
    """Build a minimal but realistic application state dict."""
    x = np.linspace(100.0, 3500.0, n_points)
    spectra = [
        {
            'label': f'test : {str(i).zfill(4)}',
            'x_scale': np.linspace(100.0, 3500.0, n_points),
            'y_scale': np.random.rand(n_points),
            'metadata': {
                'file_path': 'test.txt',
                'valid_points': n_points,
                'unique_id': f'uid-{i}',
            },
        }
        for i in range(1, n_spectra + 1)
    ]
    return {
        'timestamp': '2026-05-21T10:00:00',
        'original_spectra': spectra,
        'selected_spectra': spectra[:1],
        'selected_indices': [0],
        'plot_settings': {
            'plot_type': 'Overlay plot',
            'use_automatic_line_colors': True,
            'use_default_points': False,
            'x_scale': 'linear',
            'y_scale': 'linear',
            'grid_settings': {'rows': 1, 'columns': 1},
            'spectra_ordering': 'Alphabetical',
            'reverse_order': False,
        },
        'link_axes': {
            'link_x': False,
            'link_y': False,
            'link_x_direction': 'all',
            'link_y_direction': 'all',
        },
    }


# ---------------------------------------------------------------------------
# Encoder / decoder unit tests
# ---------------------------------------------------------------------------

class TestJsonEncoderDecoder:
    def test_numpy_array_encodes_to_dict(self):
        arr = np.array([1.0, 2.0, 3.0])
        encoded = SaveManager._json_encode(arr)
        assert isinstance(encoded, dict)
        assert encoded['__ndarray__'] is True
        assert 'data' in encoded
        assert 'dtype' in encoded
        assert 'shape' in encoded

    def test_numpy_array_round_trip(self):
        arr = np.array([100.0, 200.0, 300.0], dtype='float64')
        encoded = SaveManager._json_encode(arr)
        decoded = SaveManager._json_decode(encoded)
        assert isinstance(decoded, np.ndarray)
        np.testing.assert_allclose(decoded, arr)

    def test_numpy_integer_scalar(self):
        val = np.int64(42)
        result = SaveManager._json_encode(val)
        assert result == 42
        assert isinstance(result, int)

    def test_numpy_float_scalar(self):
        val = np.float64(3.14)
        result = SaveManager._json_encode(val)
        assert abs(result - 3.14) < 1e-10
        assert isinstance(result, float)

    def test_non_ndarray_passes_through_decode(self):
        obj = {'key': 'value', 'number': 42}
        assert SaveManager._json_decode(obj) == obj

    def test_2d_array_shape_preserved(self):
        arr = np.random.rand(10, 5)
        encoded = SaveManager._json_encode(arr)
        decoded = SaveManager._json_decode(encoded)
        assert decoded.shape == (10, 5)
        np.testing.assert_allclose(decoded, arr)

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            SaveManager._json_encode(object())


# ---------------------------------------------------------------------------
# Full JSON serialisation round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_state_serialises_to_string(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        assert isinstance(text, str)
        assert text.startswith('{')

    def test_state_deserialises_from_string(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        assert isinstance(restored, dict)
        assert 'original_spectra' in restored

    def test_numpy_arrays_restored(self):
        state = _make_state(n_spectra=2, n_points=20)
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        for orig, rest in zip(state['original_spectra'],
                               restored['original_spectra']):
            assert isinstance(rest['x_scale'], np.ndarray)
            assert isinstance(rest['y_scale'], np.ndarray)
            np.testing.assert_allclose(rest['x_scale'], orig['x_scale'])
            np.testing.assert_allclose(rest['y_scale'], orig['y_scale'])

    def test_plain_values_preserved(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        assert restored['plot_settings']['plot_type'] == 'Overlay plot'
        assert restored['plot_settings']['use_automatic_line_colors'] is True
        assert restored['selected_indices'] == [0]

    def test_labels_preserved(self):
        state = _make_state(n_spectra=3)
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        orig_labels = [sp['label'] for sp in state['original_spectra']]
        rest_labels = [sp['label'] for sp in restored['original_spectra']]
        assert orig_labels == rest_labels

    def test_metadata_preserved(self):
        state = _make_state()
        text = SaveManager._to_json(state)
        restored = SaveManager._from_json(text)
        orig_meta = state['original_spectra'][0]['metadata']
        rest_meta = restored['original_spectra'][0]['metadata']
        assert rest_meta['file_path'] == orig_meta['file_path']
        assert rest_meta['valid_points'] == orig_meta['valid_points']


# ---------------------------------------------------------------------------
# File save / load round-trip
# ---------------------------------------------------------------------------

class TestSnapshotFileSaveLoad:
    def test_file_written(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state()
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        assert os.path.exists(tmp_snapx)
        assert os.path.getsize(tmp_snapx) > 0

    def test_file_starts_with_brace(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state()
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        with open(tmp_snapx, 'rb') as f:
            assert f.read(1) == b'{'

    def test_load_state_reads_json(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state(n_spectra=2, n_points=10)
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        loaded = mgr._load_state(tmp_snapx)
        assert 'original_spectra' in loaded
        assert len(loaded['original_spectra']) == 2

    def test_load_state_restores_arrays(self, tmp_snapx):
        mgr = SaveManager()
        state = _make_state(n_spectra=1, n_points=20)
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        loaded = mgr._load_state(tmp_snapx)
        x_orig = state['original_spectra'][0]['x_scale']
        x_load = loaded['original_spectra'][0]['x_scale']
        assert isinstance(x_load, np.ndarray)
        np.testing.assert_allclose(x_load, x_orig)

    def test_invalid_file_raises_friendly_error(self, tmp_snapx):
        """Any non-JSON file must raise a clear, friendly error -- this
        format has no legacy fallback of any kind, so garbage bytes are
        rejected the same way a wrong-format file would be."""
        with open(tmp_snapx, 'wb') as f:
            f.write(b'not a snapshot file, just some random garbage bytes')
        mgr = SaveManager()
        with pytest.raises(ValueError, match="not a valid snapshot"):
            mgr._load_state(tmp_snapx)

    def test_excel_file_raises_friendly_error(self, tmp_xlsx):
        """Passing an Excel file as a snapshot must give a clear error."""
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            wb.save(tmp_xlsx)
            mgr = SaveManager()
            with pytest.raises(ValueError, match="not a valid snapshot"):
                mgr._load_state(tmp_xlsx)
        except ImportError:
            pytest.skip("openpyxl not installed")


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

class TestSnapshotPerformance:
    def test_large_snapshot_speed(self, tmp_snapx):
        """1000 spectra × 500 points must save and load in under 3 seconds."""
        import time
        mgr = SaveManager()
        state = _make_state(n_spectra=1000, n_points=500)

        t0 = time.time()
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        save_time = time.time() - t0

        t0 = time.time()
        loaded = mgr._load_state(tmp_snapx)
        load_time = time.time() - t0

        assert save_time < 3.0, f"Save took {save_time:.1f}s"
        assert load_time < 3.0, f"Load took {load_time:.1f}s"
        assert len(loaded['original_spectra']) == 1000


# ---------------------------------------------------------------------------
# Fakes for controller-level tests below -- no QApplication needed.
# Mirror the small subset of the real UI/controller surface that
# save_spectra_manager.py actually touches during a save or load.
# ---------------------------------------------------------------------------

class _FakeWidget:
    """Stand-in for a Qt widget: holds one value, supports the getter/
    setter/blockSignals calls the snapshot code makes on it via
    SaveManager._safe_get / _safe_set."""

    def __init__(self, value=None):
        self._value = value
        self.signals_blocked = False

    def currentText(self):
        return self._value

    def setCurrentText(self, v):
        self._value = v

    def isChecked(self):
        return bool(self._value)

    def setChecked(self, v):
        self._value = v

    def value(self):
        return self._value

    def setValue(self, v):
        self._value = v

    def blockSignals(self, flag):
        self.signals_blocked = flag


class _FakeUI:
    def __init__(self, plot_type='Overlay plot', rows=1, columns=1):
        self.comboBox_plot_type_choice = _FakeWidget(plot_type)
        self.number_of_rows_spinBox = _FakeWidget(rows)
        self.number_of_columns_spinBox = _FakeWidget(columns)
        self.x_scale_comboBox = _FakeWidget('linear')
        self.y_scale_comboBox = _FakeWidget('linear')
        self.automatic_line_colors_checkBox = _FakeWidget(True)
        self.comboBox_spectra_ordering = _FakeWidget('Alphabetical')
        self.checkBox_reverse_order = _FakeWidget(False)
        self.link_x_axes_checkBox = _FakeWidget(False)
        self.link_y_axes_checkBox = _FakeWidget(False)
        self.comboBox_linking_x_axes = _FakeWidget('all')
        self.comboBox_linking_y_axes = _FakeWidget('all')


class _FakeSpectrumSelector:
    def __init__(self):
        self.selected_indices = set()
        self.is_batch_updating = False

    def update_spectra_count_label(self):
        pass


class _FakeMainController:
    """Stand-in for the main window controller. Counts calls to
    plot_spectra() / update_grid_layout() so tests can assert exactly how
    many full re-renders a snapshot load triggers."""

    def __init__(self, plot_type='Overlay plot', selected_spectra=None,
                 original_spectra=None, rows=1, columns=1):
        self.view = _FakeUI(plot_type=plot_type, rows=rows, columns=columns)
        self.original_spectra = original_spectra or []
        self.selected_spectra = selected_spectra or []
        self.grid_settings = {'rows': rows, 'columns': columns}
        self.use_automatic_line_colors = True
        self.use_default_points = False
        self.spectrum_selector = _FakeSpectrumSelector()
        self.plot_spectra_calls = 0
        self.update_grid_layout_calls = 0
        self.last_progress_callback = 'UNSET'

    def plot_spectra(self, progress_callback=None):
        self.plot_spectra_calls += 1
        self.last_progress_callback = progress_callback

    def update_grid_layout(self):
        self.update_grid_layout_calls += 1
        self.grid_settings['rows'] = self.view.number_of_rows_spinBox.value()
        self.grid_settings['columns'] = self.view.number_of_columns_spinBox.value()
        self.plot_spectra()


def _make_spectra(n=2, n_points=10, label_prefix='s'):
    x = np.linspace(100.0, 500.0, n_points)
    return [
        {
            'label': f'{label_prefix}{i}',
            'x_scale': x.copy(),
            'y_scale': np.random.rand(n_points),
            'metadata': {'unique_id': f'uid-{label_prefix}{i}'},
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Duplicate-label rejection
#
# Every normal path in the app that creates or renames a spectrum
# guarantees unique labels -- but a snapshot's original_spectra is restored
# via direct assignment, bypassing those guards. A snapshot with duplicate
# labels can only mean the file was hand-edited or corrupted, so it must be
# refused cleanly rather than silently proceeding.
# ---------------------------------------------------------------------------

class TestValidateUniqueLabels:
    def test_raises_on_duplicate_labels(self):
        mgr = SaveManager()
        spectra = [
            {'label': 'dup', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]), 'metadata': {}},
            {'label': 'dup', 'x_scale': np.array([2.0]), 'y_scale': np.array([2.0]), 'metadata': {}},
        ]
        with pytest.raises(ValueError, match="dup"):
            mgr._validate_unique_labels(spectra)

    def test_passes_with_unique_labels(self):
        mgr = SaveManager()
        spectra = _make_spectra(3)
        mgr._validate_unique_labels(spectra)  # must not raise


# ---------------------------------------------------------------------------
# SpectrumManager resync
#
# main_controller.original_spectra is reassigned directly on load, which
# bypasses SpectrumManager's own bookkeeping (self.spectra, id_to_label_map,
# label_to_id_map). _resync_spectrum_manager rebuilds that bookkeeping so it
# doesn't go stale after a snapshot load.
# ---------------------------------------------------------------------------

class _FakeSpectrumManager:
    def __init__(self):
        self.spectra = {}
        self.id_to_label_map = {}
        self.label_to_id_map = {}

    def clear_spectra(self):
        self.spectra.clear()
        self.id_to_label_map.clear()
        self.label_to_id_map.clear()


class TestResyncSpectrumManager:
    def test_rebuilds_bookkeeping_from_restored_spectra(self):
        mgr = SaveManager()
        fake_sm = _FakeSpectrumManager()
        fake_sm.spectra['stale_leftover'] = object()
        fake_main = SimpleNamespace(
            import_controller=SimpleNamespace(spectrum_manager=fake_sm)
        )
        spectra = _make_spectra(2, label_prefix='sp')

        mgr._resync_spectrum_manager(fake_main, spectra)

        assert 'stale_leftover' not in fake_sm.spectra
        assert set(fake_sm.spectra.keys()) == {'sp0', 'sp1'}
        assert fake_sm.id_to_label_map['uid-sp0'] == 'sp0'
        assert fake_sm.label_to_id_map['sp0'] == 'uid-sp0'

    def test_noop_when_no_spectrum_manager_present(self):
        mgr = SaveManager()
        fake_main = SimpleNamespace()  # no import_controller at all
        # Must return quietly rather than raising.
        mgr._resync_spectrum_manager(fake_main, _make_spectra(1))


# ---------------------------------------------------------------------------
# Operations-baseline dedup (_build_state)
#
# operations_manager.original_spectra (the pre-operations baseline) used to
# always be written into the snapshot alongside the top-level
# original_spectra, even when the operations chain was empty and the two
# were identical -- doubling every spectrum's array data in the file for
# nothing. It's now only written when it actually differs.
# ---------------------------------------------------------------------------

class TestSpectraListsEqual:
    """Unit tests for the exhaustive equality check itself, independent of
    _build_state -- it has to get numpy arrays, nested metadata, and
    ambiguous comparisons right on its own before anything can trust it."""

    def test_identical_content_different_objects_is_equal(self):
        mgr = SaveManager()
        a = _make_spectra(2)
        b = [dict(s, x_scale=s['x_scale'].copy(), y_scale=s['y_scale'].copy(),
                   metadata=dict(s['metadata']))
             for s in a]
        assert mgr._spectra_lists_equal(a, b) is True

    def test_different_length_is_not_equal(self):
        mgr = SaveManager()
        a = _make_spectra(2)
        b = _make_spectra(3)
        assert mgr._spectra_lists_equal(a, b) is False

    def test_different_y_scale_is_not_equal(self):
        mgr = SaveManager()
        a = _make_spectra(2, label_prefix='x')
        b = _make_spectra(2, label_prefix='x')  # random y_scale differs
        assert mgr._spectra_lists_equal(a, b) is False

    def test_metadata_only_difference_is_detected(self):
        """The exact gap the old label/x_scale/y_scale-only check had:
        identical label and identical arrays, but different metadata."""
        mgr = SaveManager()
        a = _make_spectra(1)
        b = [dict(a[0], x_scale=a[0]['x_scale'].copy(),
                   y_scale=a[0]['y_scale'].copy(),
                   metadata=dict(a[0]['metadata'], correction_history=['Rename']))]
        assert mgr._spectra_lists_equal(a, b) is False

    def test_nan_in_array_does_not_break_the_comparison(self):
        mgr = SaveManager()
        a = [{'label': 's', 'x_scale': np.array([1.0, np.nan]),
              'y_scale': np.array([1.0, 2.0]), 'metadata': {}}]
        b = [{'label': 's', 'x_scale': np.array([1.0, np.nan]),
              'y_scale': np.array([1.0, 2.0]), 'metadata': {}}]
        assert mgr._spectra_lists_equal(a, b) is True

    def test_nested_array_in_metadata_is_compared_correctly(self):
        """A numpy array nested inside metadata used to be able to trigger
        Python's 'truth value of an array is ambiguous' error under a
        naive comparison -- must be handled, not just avoided by luck."""
        mgr = SaveManager()
        a = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'duplicate_x_merge': {'merged_at': np.array([1, 2, 3])}}}]
        b = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'duplicate_x_merge': {'merged_at': np.array([1, 2, 3])}}}]
        c = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'duplicate_x_merge': {'merged_at': np.array([1, 2, 4])}}}]
        assert mgr._spectra_lists_equal(a, b) is True
        assert mgr._spectra_lists_equal(a, c) is False

    def test_extra_metadata_key_is_not_equal(self):
        mgr = SaveManager()
        a = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'unique_id': 'u1'}}]
        b = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'unique_id': 'u1', 'note': 'added later'}}]
        assert mgr._spectra_lists_equal(a, b) is False

    def test_uncomparable_values_fail_toward_not_equal(self):
        """Anything the comparison can't confidently judge must count as
        NOT equal (the safe direction -- keep both copies) rather than
        risk a false 'they're the same'."""
        class _NoEquality:
            def __eq__(self, other):
                raise TypeError("cannot compare")

        mgr = SaveManager()
        a = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'weird': _NoEquality()}}]
        b = [{'label': 's', 'x_scale': np.array([1.0]), 'y_scale': np.array([1.0]),
              'metadata': {'weird': _NoEquality()}}]
        assert mgr._spectra_lists_equal(a, b) is False


class TestOperationsBaselineDedup:
    """
    Whether the pre-operations baseline gets saved separately from the
    top-level original_spectra is decided by comparing the two lists'
    actual content, completely (see _spectra_lists_equal and
    TestSpectraListsEqual above) -- not by checking whether the
    operations chain happens to be empty. That was tried first and
    rejected: it depended on an assumption this file can't verify (that
    every other part of the app keeps the two lists in sync whenever the
    chain is empty), and this codebase has a documented history of
    exactly that kind of desync. A direct content comparison doesn't need
    that assumption at all -- whatever the chain says, identical content
    is deduped and different content (in ANY field) is kept.
    """

    def _controller_with_operations(self, baseline_spectra, current_spectra,
                                      operations_chain=None):
        controller = _FakeMainController(
            plot_type='Overlay plot',
            selected_spectra=current_spectra[:1],
            original_spectra=current_spectra,
        )
        ops_manager = SimpleNamespace(
            original_spectra=baseline_spectra,
            operations_chain=operations_chain or [],
            active_operation_index=-1 if not operations_chain else 0,
            import_batches=[],
        )
        controller.operations_controller = SimpleNamespace(
            operations_manager=ops_manager,
            current_parameters={},
        )
        return controller

    def test_identical_content_is_not_duplicated(self):
        mgr = SaveManager()
        spectra = _make_spectra(2)
        # Same content, deliberately different list/dict objects.
        baseline_copy = [dict(s) for s in spectra]
        controller = self._controller_with_operations(
            baseline_spectra=baseline_copy, current_spectra=spectra,
        )

        state = mgr._build_state(controller)

        assert 'original_spectra' not in state['operations']

    def test_different_numeric_data_is_kept(self):
        mgr = SaveManager()
        current = _make_spectra(2, label_prefix='cur')
        baseline = _make_spectra(2, label_prefix='cur')  # different y_scale
        controller = self._controller_with_operations(
            baseline_spectra=baseline, current_spectra=current,
        )

        state = mgr._build_state(controller)

        assert 'original_spectra' in state['operations']
        assert state['operations']['original_spectra'] is baseline

    def test_metadata_only_difference_is_kept_even_with_empty_chain(self):
        """The exact scenario the old chain-based check would have gotten
        wrong: labels and arrays identical, only metadata differs, and
        the chain is (incorrectly, for this test) reported as empty. The
        content comparison doesn't care what the chain says."""
        mgr = SaveManager()
        current = _make_spectra(1, label_prefix='cur')
        baseline = [dict(current[0],
                          x_scale=current[0]['x_scale'].copy(),
                          y_scale=current[0]['y_scale'].copy(),
                          metadata=dict(current[0]['metadata'], edited=True))]
        controller = self._controller_with_operations(
            baseline_spectra=baseline, current_spectra=current,
            operations_chain=[],  # deliberately empty -- must not matter
        )

        state = mgr._build_state(controller)

        assert 'original_spectra' in state['operations']
        assert state['operations']['original_spectra'] is baseline

    def test_identical_content_is_deduped_even_with_nonempty_chain(self):
        """The decision no longer depends on the chain at all: identical
        content is deduped whether or not an operation is recorded."""
        mgr = SaveManager()
        spectra = _make_spectra(2, label_prefix='same')
        baseline_copy = [dict(s) for s in spectra]
        controller = self._controller_with_operations(
            baseline_spectra=baseline_copy, current_spectra=spectra,
            operations_chain=[{'type': 'some_operation'}],
        )

        state = mgr._build_state(controller)

        assert 'original_spectra' not in state['operations']

# ---------------------------------------------------------------------------
# _restore_operations: defensive, and falls back to the just-restored
# original_spectra when the snapshot didn't store a separate baseline
# (see the dedup above).
# ---------------------------------------------------------------------------

class _StrictActiveIndexOpsManager:
    """operations_manager stand-in where ASSIGNING active_operation_index
    always fails -- even for a value that would otherwise validate fine
    against the incoming chain. Used to prove that a failure during the
    assignment step itself (not just a validation failure) still resets
    BOTH operations_chain and active_operation_index atomically, rather
    than leaving operations_chain updated to the new value while
    active_operation_index silently keeps its old, now-mismatched one."""

    def __init__(self):
        self.original_spectra = []
        self._operations_chain = []
        self._active_operation_index = -1

    @property
    def operations_chain(self):
        return self._operations_chain

    @operations_chain.setter
    def operations_chain(self, value):
        self._operations_chain = value

    @property
    def active_operation_index(self):
        return self._active_operation_index

    @active_operation_index.setter
    def active_operation_index(self, value):
        raise RuntimeError("boom")


class TestRestoreOperationsDefensive:
    def test_defaults_baseline_to_restored_original_spectra_when_absent(self):
        mgr = SaveManager()
        restored_original = _make_spectra(2)
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = SimpleNamespace(
            operations_controller=SimpleNamespace(operations_manager=ops_manager,
                                                    current_parameters={}),
            original_spectra=restored_original,
        )

        mgr._restore_operations(fake_main, {'operations_chain': [], 'active_operation_index': -1})

        assert ops_manager.original_spectra is restored_original

    def test_uses_stored_baseline_when_present(self):
        mgr = SaveManager()
        stored_baseline = _make_spectra(2, label_prefix='baseline')
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = SimpleNamespace(
            operations_controller=SimpleNamespace(operations_manager=ops_manager,
                                                    current_parameters={}),
            original_spectra=_make_spectra(2, label_prefix='current'),
        )

        mgr._restore_operations(fake_main, {'original_spectra': stored_baseline})

        assert ops_manager.original_spectra is stored_baseline

    def test_unrelated_field_failure_does_not_abort_the_rest(self):
        # current_parameters is still restored independently -- a failure
        # restoring it (or original_spectra) must not prevent the
        # operations_chain/active_operation_index pair (or anything else)
        # from restoring.
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)

        class _StrictParamsController:
            def __init__(self):
                self.operations_manager = ops_manager

            @property
            def current_parameters(self):
                return self._current_parameters

            @current_parameters.setter
            def current_parameters(self, value):
                raise RuntimeError("boom")

        op = _StrictParamsController()
        fake_main = SimpleNamespace(operations_controller=op, original_spectra=[])
        chain = [{'type': 'baseline_correction', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {
            'operations_chain': chain,
            'active_operation_index': 0,
            'current_parameters': {'foo': 'bar'},  # always fails to set
        })  # must not raise

        assert ops_manager.operations_chain == chain
        assert ops_manager.active_operation_index == 0


# ---------------------------------------------------------------------------
# _restore_operations: operations_chain and active_operation_index are
# restored as a single atomic, mutually-validated pair (unlike the other
# fields above, which restore independently). get_current_spectra() does
# a direct self.operations_chain[self.active_operation_index] lookup with
# no bounds check, so a mismatched pair -- one restored, the other stale
# or failed -- wouldn't raise here, but could raise IndexError later, far
# from the snapshot load that actually caused it. These tests cover every
# way the pair can fail to line up, and confirm each one resets BOTH
# fields to a safe, consistent state ([], -1) instead of leaving a
# mismatch behind.
# ---------------------------------------------------------------------------

class TestOperationsChainIndexAtomicity:
    @staticmethod
    def _fake_main(ops_manager):
        return SimpleNamespace(
            operations_controller=SimpleNamespace(
                operations_manager=ops_manager, current_parameters={}),
            original_spectra=[],
        )

    def test_valid_pair_restores_as_is(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []},
                 {'type': 'op2', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 1})

        assert ops_manager.operations_chain == chain
        assert ops_manager.active_operation_index == 1

    def test_index_out_of_range_high_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 5})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_index_below_minus_one_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': -2})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_chain_wrong_type_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[{'stale': True}],
                                       active_operation_index=0)
        fake_main = self._fake_main(ops_manager)

        mgr._restore_operations(fake_main, {'operations_chain': "not-a-list", 'active_operation_index': 0})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_index_wrong_type_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[{'stale': True}],
                                       active_operation_index=0)
        fake_main = self._fake_main(ops_manager)

        mgr._restore_operations(fake_main, {
            'operations_chain': [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}],
            'active_operation_index': "1",
        })

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_index_as_bool_resets_both(self):
        # bool is technically an int subclass in Python -- explicitly
        # rejected so True/False can never sneak in as 1/0.
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)

        mgr._restore_operations(fake_main, {
            'operations_chain': [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}],
            'active_operation_index': False,
        })

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_missing_index_falls_back_to_managers_current_value_and_validates_it(self):
        # A hand-edited snapshot might have 'operations_chain' but not
        # 'active_operation_index' in its ops dict. The manager's own
        # current index is then used as the "new" value and must still be
        # validated against the new chain, not left untouched unchecked.
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain})

        assert ops_manager.operations_chain == chain
        assert ops_manager.active_operation_index == -1

    def test_missing_index_that_is_stale_and_incompatible_resets_both(self):
        # The manager's pre-existing active_operation_index (3) is not
        # valid for the new, shorter chain being restored, and only
        # 'operations_chain' is present in ops -- this must still be
        # caught, not skipped just because the index key is absent.
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[],
                                       operations_chain=[{}, {}, {}, {}],
                                       active_operation_index=3)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}]  # length 1: index 3 no longer valid

        mgr._restore_operations(fake_main, {'operations_chain': chain})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_assignment_failure_resets_both_atomically(self):
        # operations_chain assigns fine and active_operation_index would
        # validate fine (0 is in range for a 1-entry chain), but the
        # assignment of active_operation_index itself always raises.
        # operations_chain must NOT be left holding the new value while
        # active_operation_index failed to follow it to a matching state.
        mgr = SaveManager()
        ops_manager = _StrictActiveIndexOpsManager()
        fake_main = self._fake_main(ops_manager)

        mgr._restore_operations(fake_main, {
            'operations_chain': [{'type': 'baseline_correction', 'parameters': {}, 'affected_labels': [], 'output_spectra': []}],
            'active_operation_index': 0,
        })  # must not raise

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_other_fields_still_restore_independently_when_pair_is_reset(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = SimpleNamespace(
            operations_controller=SimpleNamespace(operations_manager=ops_manager,
                                                    current_parameters={}),
            original_spectra=[],
        )

        mgr._restore_operations(fake_main, {
            'operations_chain': [{'type': 'op1'}],
            'active_operation_index': 99,  # invalid -> pair resets
            'current_parameters': {'foo': 'bar'},
        })

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1
        assert fake_main.operations_controller.current_parameters == {'foo': 'bar'}

    # -- Per-entry shape validation ---------------------------------------
    # The chain/index pairing can be perfectly valid (index in range) while
    # an individual entry is still malformed in a way that crashes a
    # DIFFERENT consumer later: IncrementalOperationsManager.
    # set_active_operation() and get_operation_description() read
    # operation['type']/['parameters'] directly (no .get() fallback), and
    # OperationsSummaryDialog reads operation['affected_labels'] directly
    # in a couple of places. So each entry's minimal shape is validated
    # too, not just the chain's length against the index.

    def test_entry_missing_type_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'parameters': {}, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 0})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_entry_not_a_dict_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = ["not-a-dict"]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 0})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_entry_parameters_wrong_type_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': None, 'affected_labels': [], 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 0})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_entry_output_spectra_wrong_type_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': None}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 0})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_entry_affected_labels_wrong_type_resets_both(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [{'type': 'op1', 'parameters': {}, 'affected_labels': None, 'output_spectra': []}]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 0})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_one_bad_entry_among_good_ones_resets_the_whole_chain(self):
        # The pair is restored atomically as a whole -- a single malformed
        # entry anywhere in the chain resets ALL of it, not just the bad
        # entry, since active_operation_index's validity depends on the
        # chain's length as a whole, not on any one entry.
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [
            {'type': 'op1', 'parameters': {}, 'affected_labels': [], 'output_spectra': []},
            {'type': 'op2', 'affected_labels': [], 'output_spectra': []},  # missing 'parameters'
        ]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 1})

        assert ops_manager.operations_chain == []
        assert ops_manager.active_operation_index == -1

    def test_well_formed_entries_restore_fine(self):
        mgr = SaveManager()
        ops_manager = SimpleNamespace(original_spectra=[], operations_chain=[],
                                       active_operation_index=-1)
        fake_main = self._fake_main(ops_manager)
        chain = [
            {'type': 'Normalization', 'parameters': {'method': 'max'},
             'affected_labels': ['a'], 'output_spectra': []},
            {'type': 'Data range', 'parameters': {'start': 100, 'end': 200},
             'affected_labels': ['a', 'b'], 'output_spectra': []},
        ]

        mgr._restore_operations(fake_main, {'operations_chain': chain, 'active_operation_index': 1})

        assert ops_manager.operations_chain == chain
        assert ops_manager.active_operation_index == 1


# ---------------------------------------------------------------------------
# Single render per snapshot load (performance fix)
#
# Loading used to trigger several full re-renders of the plot for one load
# (a call inside _restore_ui_state, a "set spinbox to 1 then back" trick to
# force a signal, then an explicit plot_spectra() call) -- expensive for a
# large 2D map shown in Grid plot mode, where every render rebuilds every
# subplot. load_snapshot() must now render exactly once.
# ---------------------------------------------------------------------------

class TestSingleRenderOnLoad:
    def _write_state(self, tmp_snapx, mgr, **overrides):
        spectra = _make_spectra(2)
        state = {
            'timestamp': '2026-05-21T10:00:00',
            'original_spectra': spectra,
            'selected_spectra': spectra[:1],
            'selected_indices': [0],
            'plot_settings': {
                'plot_type': 'Overlay plot',
                'use_automatic_line_colors': True,
                'use_default_points': False,
                'x_scale': 'linear',
                'y_scale': 'linear',
                'grid_settings': {'rows': 2, 'columns': 3},
                'spectra_ordering': 'Alphabetical',
                'reverse_order': False,
            },
            'link_axes': {
                'link_x': False, 'link_y': False,
                'link_x_direction': 'all', 'link_y_direction': 'all',
            },
        }
        state.update(overrides)
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)
        return state

    def test_grid_plot_renders_exactly_once(self, tmp_snapx):
        mgr = SaveManager()
        state = self._write_state(tmp_snapx, mgr)
        state['plot_settings']['plot_type'] = 'Grid plot'
        text = mgr._to_json(state)
        with open(tmp_snapx, 'w', encoding='utf-8') as f:
            f.write(text)

        controller = _FakeMainController(plot_type='Grid plot')
        mgr.load_snapshot(controller, tmp_snapx)

        # The render always goes through plot_spectra() directly now,
        # for every plot type including Grid -- _restore_ui_state
        # already restored main_controller.grid_settings (and the
        # spinbox values) above, so a separate update_grid_layout()
        # call would only redo that same read and then call
        # plot_spectra() anyway. See the comment at the call site in
        # save_spectra_manager.py.
        assert controller.update_grid_layout_calls == 0
        assert controller.plot_spectra_calls == 1
        # The restored row/col values actually took effect.
        assert controller.grid_settings == {'rows': 2, 'columns': 3}

    def test_overlay_plot_renders_exactly_once(self, tmp_snapx):
        mgr = SaveManager()
        self._write_state(tmp_snapx, mgr)

        controller = _FakeMainController(plot_type='Overlay plot')
        mgr.load_snapshot(controller, tmp_snapx)

        assert controller.update_grid_layout_calls == 0
        assert controller.plot_spectra_calls == 1

    def test_no_render_when_nothing_selected(self, tmp_snapx):
        mgr = SaveManager()
        self._write_state(tmp_snapx, mgr, selected_spectra=[])

        controller = _FakeMainController(plot_type='Overlay plot')
        mgr.load_snapshot(controller, tmp_snapx)

        assert controller.plot_spectra_calls == 0
        assert controller.update_grid_layout_calls == 0

    def test_render_progress_callback_is_forwarded_to_plot_spectra(self, tmp_snapx):
        # A large 2D map's Grid render can itself take long enough that
        # the caller's progress dialog needs pumping *during* it, not
        # just before/after -- plot_spectra()'s own progress_callback
        # parameter (a no-arg pump, forwarded to grid_plot_mode /
        # overlay_plot_mode's per-item notify_progress() calls) is how.
        # That's a different contract from load_snapshot()'s own
        # (stage, label) progress_callback, so load_snapshot() must
        # adapt one into the other rather than passing either straight
        # through as the other.
        mgr = SaveManager()
        self._write_state(tmp_snapx, mgr)
        controller = _FakeMainController(plot_type='Overlay plot')

        stage_calls = []
        mgr.load_snapshot(
            controller, tmp_snapx,
            progress_callback=lambda stage, label: stage_calls.append((stage, label)))

        assert callable(controller.last_progress_callback)
        calls_before = len(stage_calls)
        controller.last_progress_callback()
        assert stage_calls[calls_before:] == [
            (SaveManager.LOAD_SNAPSHOT_STAGE_COUNT, "Rendering plot…")]

    def test_no_render_progress_callback_when_caller_passed_none(self, tmp_snapx):
        mgr = SaveManager()
        self._write_state(tmp_snapx, mgr)
        controller = _FakeMainController(plot_type='Overlay plot')

        mgr.load_snapshot(controller, tmp_snapx)  # no progress_callback at all

        assert controller.last_progress_callback is None


# ---------------------------------------------------------------------------
# _restore_spectrum_selection(): showing the spectrum-selection panel
#
# The panel must become visible as soon as the list is actually populated
# (stage 5), not afterwards -- see the comment at the call site in
# save_spectra_manager.py. Leaving it to ImportController.import_snapshot()
# (after the plot render *and* the "Snapshot Loaded" dialog) meant a large
# snapshot's one-time first-ever panel layout cost landed on top of the
# render delay instead of underneath the still-open progress dialog.
# ---------------------------------------------------------------------------

class TestRestoreSpectrumSelectionShowsPanel:
    def _controller(self, n=3):
        main_controller = MagicMock()
        main_controller.original_spectra = _make_spectra(n)
        main_controller.spectrum_selector.selected_indices = set()
        main_controller.spectra_list_widget.count.return_value = n
        return main_controller

    def test_panel_made_visible_after_list_is_populated(self):
        mgr = SaveManager()
        main_controller = self._controller()
        with patch('PyQt5.QtWidgets.QListWidgetItem'), patch('PyQt5.QtCore.Qt'):
            mgr._restore_spectrum_selection(main_controller, {'selected_indices': [0]})

        main_controller.view.spectrum_selection_frame.setVisible.assert_called_once_with(True)

    def test_missing_spectra_list_widget_skips_silently(self):
        # No spectra_list_widget attribute at all -- the pre-existing
        # early-return path. Must not raise, and must not even look at
        # `view` since it never gets that far.
        mgr = SaveManager()
        main_controller = SimpleNamespace(original_spectra=[])
        mgr._restore_spectrum_selection(main_controller, {})  # no exception

    def test_display_failure_does_not_abort_the_restore(self):
        # A problem showing the panel is cosmetic, not a reason to fail
        # an otherwise-successful stage-5 restore.
        mgr = SaveManager()
        main_controller = self._controller()
        main_controller.view.spectrum_selection_frame.setVisible.side_effect = RuntimeError("boom")
        with patch('PyQt5.QtWidgets.QListWidgetItem'), patch('PyQt5.QtCore.Qt'):
            mgr._restore_spectrum_selection(main_controller, {'selected_indices': [0]})  # no exception
        main_controller.spectrum_selector.update_spectra_count_label.assert_called_once()


# ---------------------------------------------------------------------------
# Controller-level behavior (no QApplication needed for either class below)
# ---------------------------------------------------------------------------

class TestSaveControllerLoadSnapshot:
    """SaveController.load_snapshot(): the confirm/error/success flow, and
    that a successful load never falls through a dead `return False` (the
    manager's load_snapshot() only ever returns True or raises).

    The confirmation is now a QMessageBox instance (built manually, not
    the static .question() convenience) so a "?" help button can be
    added to it -- these tests mock the instance's addButton/
    clickedButton() pair rather than .question()'s return value.
    QPushButton is also mocked: a real one can't be constructed without a
    running QApplication, which these tests deliberately don't create.

    Note what this class deliberately does NOT do: assert that
    clear_graphics_view() / spectra_list_widget.clear() are called before
    the load. An earlier version called them right after confirming, to
    keep the old workspace from sitting on screen during a slow load --
    but clearing spectra_list_widget turned out to fire
    itemSelectionChanged, which SpectrumSelectorController reacts to by
    overwriting main_controller.selected_spectra with an empty list. A
    load that then failed had no real selection to show back. The old
    workspace is left completely untouched now, exactly like a regular
    data import, until SaveManager.load_snapshot() itself replaces
    everything on success -- see the comment at that call site.
    """

    def _controller(self):
        from src.controllers.misc.save_spectra_controller import SaveController
        controller = SaveController(main_controller=MagicMock())
        controller.save_manager = MagicMock()
        return controller

    def _patches(self):
        return (
            patch('src.controllers.misc.save_spectra_controller.QMessageBox'),
            patch('src.controllers.misc.save_spectra_controller.QPushButton'),
            patch('src.controllers.misc.save_spectra_controller.QProgressDialog'),
            patch('src.controllers.misc.save_spectra_controller.QApplication'),
        )

    def _simulate_click(self, mock_mb, clicked_is_yes: bool):
        """Configure the mocked QMessageBox instance so clickedButton()
        returns the same object load_snapshot() captured as yes_button
        (== msg_box.addButton(QMessageBox.Yes), the first addButton()
        call) when clicked_is_yes, or a distinct sentinel otherwise."""
        msg_box = mock_mb.return_value
        if clicked_is_yes:
            msg_box.clickedButton.return_value = msg_box.addButton.return_value
        else:
            msg_box.clickedButton.return_value = object()

    def test_success_returns_true_and_shows_confirmation(self):
        controller = self._controller()
        controller.save_manager.load_snapshot.return_value = True
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3, p4:
            self._simulate_click(mock_mb, clicked_is_yes=True)
            result = controller.load_snapshot("dummy.snapx")

        assert result is True
        mock_mb.return_value.exec_.assert_called_once()
        mock_mb.information.assert_called_once()
        mock_mb.critical.assert_not_called()

    def test_declining_confirmation_returns_false_without_loading(self):
        controller = self._controller()
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3, p4:
            self._simulate_click(mock_mb, clicked_is_yes=False)
            result = controller.load_snapshot("dummy.snapx")

        assert result is False
        controller.save_manager.load_snapshot.assert_not_called()

    def test_runtime_error_returns_false_and_shows_error(self):
        controller = self._controller()
        controller.save_manager.load_snapshot.side_effect = RuntimeError("bad file")
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3 as mock_pd, p4:
            self._simulate_click(mock_mb, clicked_is_yes=True)
            result = controller.load_snapshot("dummy.snapx")

        assert result is False
        mock_mb.critical.assert_called_once()
        mock_mb.information.assert_not_called()
        # The progress dialog must still be closed on the error path, not
        # left on screen after the error message box appears.
        mock_pd.return_value.close.assert_called_once()

    def test_does_not_touch_the_old_workspace_before_confirming_success(self):
        # Nothing is cleared or otherwise touched before the load starts
        # -- not on a decline, and not even on the way into a load that
        # will go on to succeed. Only SaveManager.load_snapshot() (a
        # separate call, mocked here) is responsible for actually
        # replacing anything.
        controller = self._controller()
        controller.save_manager.load_snapshot.return_value = True
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3, p4:
            self._simulate_click(mock_mb, clicked_is_yes=True)
            controller.load_snapshot("dummy.snapx")

        controller.controller.clear_graphics_view.assert_not_called()
        controller.controller.spectra_list_widget.clear.assert_not_called()

    def test_passes_progress_callback_through_to_save_manager(self):
        controller = self._controller()
        controller.save_manager.load_snapshot.return_value = True
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3, p4:
            self._simulate_click(mock_mb, clicked_is_yes=True)
            controller.load_snapshot("dummy.snapx")

        _, kwargs = controller.save_manager.load_snapshot.call_args
        assert callable(kwargs.get('progress_callback'))

    def test_progress_dialog_disables_autoclose_and_autoreset(self):
        # QProgressDialog auto-closes itself (via an internal reset()) as
        # soon as setValue() reaches the dialog's maximum. Confirmed real
        # Qt behaviour, not a hypothetical: this was making the dialog
        # vanish early on every load.
        controller = self._controller()
        controller.save_manager.load_snapshot.return_value = True
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3 as mock_pd, p4:
            self._simulate_click(mock_mb, clicked_is_yes=True)
            controller.load_snapshot("dummy.snapx")

        mock_pd.return_value.setAutoClose.assert_called_once_with(False)
        mock_pd.return_value.setAutoReset.assert_called_once_with(False)

    def test_progress_range_reserves_true_100_percent_for_after_the_render(self):
        # The dialog's range goes one step PAST LOAD_SNAPSHOT_STAGE_COUNT,
        # and the true maximum is only set() after load_snapshot() has
        # actually returned -- otherwise stage LOAD_SNAPSHOT_STAGE_COUNT
        # ("Rendering plot...") would report the same value as the
        # dialog's maximum right as its own (potentially slow) work
        # started, leaving the bar sitting at a literal 100% for however
        # long the render took, looking stuck rather than in progress.
        controller = self._controller()
        controller.save_manager.load_snapshot.return_value = True
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2, p3 as mock_pd, p4:
            self._simulate_click(mock_mb, clicked_is_yes=True)
            controller.load_snapshot("dummy.snapx")

        mock_pd.return_value.setRange.assert_called_once_with(
            0, SaveManager.LOAD_SNAPSHOT_STAGE_COUNT + 1)
        # setValue(0) at the very start, then the true maximum only after
        # the load itself has returned.
        values_set = [call.args[0] for call in mock_pd.return_value.setValue.call_args_list]
        assert values_set[0] == 0
        assert values_set[-1] == SaveManager.LOAD_SNAPSHOT_STAGE_COUNT + 1

    def test_help_button_reopens_confirmation_without_losing_it(self):
        # QMessageBox closes on ANY of its own buttons being clicked,
        # whatever that button's role -- HelpRole does NOT exempt it.
        # This was a real bug: clicking "?" closed the still-unanswered
        # "replace workspace?" question along with the info box, instead
        # of just showing the info. load_snapshot() must instead treat a
        # help click as "show the info, then ask Yes/No again" -- for as
        # many help clicks as happen, in a row.
        controller = self._controller()
        controller.save_manager.load_snapshot.return_value = True
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2 as mock_pb, p3, p4:
            msg_box = mock_mb.return_value
            yes_button = msg_box.addButton.return_value
            help_button = mock_pb.return_value
            # Help clicked twice, then Yes.
            msg_box.clickedButton.side_effect = [help_button, help_button, yes_button]

            result = controller.load_snapshot("dummy.snapx")

        assert result is True
        assert msg_box.exec_.call_count == 3
        # Two help-info popups plus the final "Snapshot Loaded" success
        # message -- all three go through this same mocked
        # QMessageBox.information, so check the first two specifically
        # rather than just a total count.
        assert mock_mb.information.call_count == 3
        help_calls = mock_mb.information.call_args_list[:2]
        assert all("About Import Snapshot" in call.args[1] for call in help_calls)
        # The actual load only ever happens once, after the real answer.
        controller.save_manager.load_snapshot.assert_called_once()

    def test_help_button_then_no_still_declines(self):
        controller = self._controller()
        p1, p2, p3, p4 = self._patches()
        with p1 as mock_mb, p2 as mock_pb, p3, p4:
            msg_box = mock_mb.return_value
            help_button = mock_pb.return_value
            no_sentinel = object()
            msg_box.clickedButton.side_effect = [help_button, no_sentinel]

            result = controller.load_snapshot("dummy.snapx")

        assert result is False
        controller.save_manager.load_snapshot.assert_not_called()


class TestImportControllerImportSnapshot:
    """ImportController.import_snapshot(): must not force the spectrum
    list visible (or do anything else) when the load didn't actually
    succeed -- previously it ignored load_snapshot()'s return value
    entirely and always applied those side effects."""

    def _controller(self):
        from src.controllers.data_io.import_controller import ImportController
        view = MagicMock()
        main_controller = MagicMock()
        return ImportController(view, main_controller), main_controller

    def test_declined_or_failed_load_has_no_side_effects(self):
        controller, main_controller = self._controller()
        main_controller.save_controller.load_snapshot.return_value = False
        with patch('src.controllers.data_io.import_controller.QFileDialog') as mock_fd:
            mock_fd.getOpenFileName.return_value = ("dummy.snapx", "")
            controller.import_snapshot()

        main_controller.view.spectrum_selection_frame.setVisible.assert_not_called()
        # The redundant re-render this method used to force on its own is gone.
        main_controller.plot_spectra.assert_not_called()
        main_controller.clear_graphics_view.assert_not_called()

    def test_successful_load_shows_spectrum_selection_frame(self):
        controller, main_controller = self._controller()
        main_controller.save_controller.load_snapshot.return_value = True
        with patch('src.controllers.data_io.import_controller.QFileDialog') as mock_fd:
            mock_fd.getOpenFileName.return_value = ("dummy.snapx", "")
            controller.import_snapshot()

        main_controller.view.spectrum_selection_frame.setVisible.assert_called_once_with(True)
        # load_snapshot() already rendered internally -- no second render here.
        main_controller.plot_spectra.assert_not_called()
        main_controller.clear_graphics_view.assert_not_called()
