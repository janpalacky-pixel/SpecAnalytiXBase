# tests/test_mat_map_converter.py
#
# Tests for reading WITec/Project FIVE hyperspectral map .mat files
# (src/modules/data_io/mat_map_converter.py).
#
# Real Project FIVE exports are large binary files unsuitable as
# committed test fixtures, so every test here builds a small synthetic
# file with scipy.io.savemat, matching exactly the struct layout real
# exports use (verified against three real files — see
# mat_map_converter.py's module docstring and _reshape_pixel_index).
# Each pixel's spectrum is set to a value that encodes its own flat
# index, so the row/col <-> pixel-index mapping is checked directly
# against known values rather than merely "it didn't crash".

import numpy as np
import pytest
import scipy.io

from src.modules.data_io.mat_map_converter import read_mat_map_data, _axis_unit_label
from src.modules.core.spectrum_manager import SpectrumManager


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

def _write_synthetic_map(
    path,
    n_dim0=4, n_dim1=3, n_wl=5,
    spectral_unit='rel. 1/cm',
    spatial_unit='um',
    include_imageaxisscale=True,
    name='synthetic test map',
    history='pytest fixture',
    n_pixels_override=None,
):
    """
    Write a minimal WITec/Project FIVE-style dataset-object .mat file.

    imagesize is [n_dim0, n_dim1] exactly as the real format stores it
    (see mat_map_converter.py: n_cols = n_dim0, n_rows = n_dim1). Each
    pixel p's spectrum is `arange(n_wl) + p * 100`, so a test can verify
    _reshape_pixel_index's row/col assignment by checking which values
    came back attached to which (row, col).
    """
    n_pixels = n_pixels_override if n_pixels_override is not None else n_dim0 * n_dim1
    data = np.zeros((n_pixels, n_wl), dtype=np.float32)
    for p in range(n_pixels):
        data[p, :] = np.arange(n_wl) + p * 100

    axisscale = np.empty((2, 2), dtype=object)
    axisscale[0, 0] = np.empty((0, 0))
    axisscale[0, 1] = np.array([''])
    axisscale[1, 0] = np.arange(1, n_wl + 1, dtype=float).reshape(1, -1) * 100.0
    axisscale[1, 1] = spectral_unit

    struct_dict = {
        'name': name,
        'type': 'image',
        'imagesize': np.array([[n_dim0, n_dim1]], dtype=np.uint8),
        'data': data,
        'axisscale': axisscale,
        'history': history,
    }

    if include_imageaxisscale:
        imageaxisscale = np.empty((2, 2), dtype=object)
        imageaxisscale[0, 0] = (np.arange(n_dim0, dtype=float) * 0.5).reshape(1, -1)
        imageaxisscale[0, 1] = spatial_unit
        imageaxisscale[1, 0] = (np.arange(n_dim1, dtype=float) * 0.2).reshape(1, -1)
        imageaxisscale[1, 1] = spatial_unit
        struct_dict['imageaxisscale'] = imageaxisscale

    scipy.io.savemat(str(path), {'test_map': struct_dict})
    return n_pixels


# ---------------------------------------------------------------------------
# Core geometry / data correctness
# ---------------------------------------------------------------------------

class TestMapGeometry:

    def test_pixel_count_and_grid_size(self, tmp_path):
        path = tmp_path / 'map.mat'
        n_pixels = _write_synthetic_map(path, n_dim0=4, n_dim1=3, n_wl=5)
        spectra = read_mat_map_data(str(path))
        assert len(spectra) == n_pixels == 12
        params = spectra[0]['metadata']['import_parameters']
        assert params['map_n_cols'] == 4
        assert params['map_n_rows'] == 3

    def test_row_col_assignment_matches_data(self, tmp_path):
        """
        The defining test: for a non-square grid, each pixel's spectrum
        (which encodes its own flat index) must end up attached to the
        (row, col) that _reshape_pixel_index says it should — row =
        index // n_cols, col = index % n_cols, n_cols = imagesize[0].
        """
        path = tmp_path / 'map.mat'
        n_dim0, n_dim1, n_wl = 4, 3, 5
        _write_synthetic_map(path, n_dim0=n_dim0, n_dim1=n_dim1, n_wl=n_wl)
        spectra = read_mat_map_data(str(path))

        n_cols = n_dim0
        seen = set()
        for sp in spectra:
            p = sp['metadata']['import_parameters']
            pixel_index = p['pixel_index']
            expected_row, expected_col = divmod(pixel_index, n_cols)
            assert p['pixel_row'] == expected_row
            assert p['pixel_col'] == expected_col
            np.testing.assert_array_equal(
                sp['y_scale'], np.arange(n_wl) + pixel_index * 100
            )
            seen.add((expected_row, expected_col))
        # Every grid cell visited exactly once.
        assert seen == {(r, c) for r in range(n_dim1) for c in range(n_dim0)}

    def test_square_map_still_reshapes_correctly(self, tmp_path):
        """A square map (n_dim0 == n_dim1) can't be used to catch a
        transposed reshape, but every pixel's index must still be
        recoverable from (row, col) — regression guard for the reshape
        order breaking silently on the common square-map case."""
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, n_dim0=5, n_dim1=5, n_wl=3)
        spectra = read_mat_map_data(str(path))
        assert len(spectra) == 25
        for sp in spectra:
            p = sp['metadata']['import_parameters']
            assert p['pixel_row'] * 5 + p['pixel_col'] == p['pixel_index']

    def test_x_scale_shared_and_correct(self, tmp_path):
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, n_dim0=2, n_dim1=2, n_wl=4)
        spectra = read_mat_map_data(str(path))
        expected_x = np.array([100., 200., 300., 400.])
        for sp in spectra:
            np.testing.assert_array_equal(sp['x_scale'], expected_x)

    def test_spectral_unit_label(self, tmp_path):
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, spectral_unit='rel. 1/cm')
        spectra = read_mat_map_data(str(path))
        assert spectra[0]['metadata']['import_parameters']['spectral_unit'] == 'rel. 1/cm'


class TestSpatialCoordinates:

    def test_spatial_coordinates_present_when_available(self, tmp_path):
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, n_dim0=4, n_dim1=3, include_imageaxisscale=True)
        spectra = read_mat_map_data(str(path))
        for sp in spectra:
            p = sp['metadata']['import_parameters']
            assert p['spatial_x'] == pytest.approx(p['pixel_col'] * 0.5)
            assert p['spatial_y'] == pytest.approx(p['pixel_row'] * 0.2)
            assert p['spatial_unit'] == 'um'

    def test_missing_imageaxisscale_degrades_gracefully(self, tmp_path):
        """A map with no imageaxisscale field is still fully importable —
        only the (informational) spatial coordinates are omitted, not the
        whole file rejected."""
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, include_imageaxisscale=False)
        spectra = read_mat_map_data(str(path))
        assert len(spectra) > 0
        assert 'spatial_x' not in spectra[0]['metadata']['import_parameters']


class TestLabelsAndMetadata:

    def test_labels_are_unique_and_zero_padded_to_grid_size(self, tmp_path):
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, n_dim0=11, n_dim1=2, n_wl=2)
        spectra = read_mat_map_data(str(path))
        labels = [sp['label'] for sp in spectra]
        assert len(set(labels)) == len(labels)
        # 11 columns needs 2 digits (0..10); single-digit row/col numbers
        # are still zero-padded to that width.
        assert any('_c00]' in lbl for lbl in labels)
        assert any('_c10]' in lbl for lbl in labels)

    def test_metadata_carries_dataset_name_and_history(self, tmp_path):
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, name='my sample', history='Created by Project FIVE (Version 5.1)')
        spectra = read_mat_map_data(str(path))
        params = spectra[0]['metadata']['import_parameters']
        assert params['dataset_name'] == 'my sample'
        assert params['source_software'] == 'Created by Project FIVE (Version 5.1)'
        assert spectra[0]['metadata']['file_type'] == 'mat_map'


# ---------------------------------------------------------------------------
# Error handling — never silently guess at a bad/foreign layout
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_not_a_mat_file_raises_clear_error(self, tmp_path):
        path = tmp_path / 'not_really.mat'
        path.write_bytes(b'this is not a MAT file at all')
        with pytest.raises(ValueError):
            read_mat_map_data(str(path))

    def test_missing_data_field_raises(self, tmp_path):
        path = tmp_path / 'map.mat'
        empty_axisscale = np.empty((2, 2), dtype=object)
        empty_axisscale[:] = [[np.empty((0, 0)), ''], [np.empty((0, 0)), '']]
        scipy.io.savemat(str(path), {'thing': {
            'imagesize': np.array([[2, 2]], dtype=np.uint8),
            'axisscale': empty_axisscale,
        }})
        with pytest.raises(ValueError, match="data"):
            read_mat_map_data(str(path))

    def test_imagesize_pixel_count_mismatch_raises(self, tmp_path):
        """imagesize claims a different pixel count than `data` actually
        has — must be rejected outright, not silently truncated/padded."""
        path = tmp_path / 'map.mat'
        _write_synthetic_map(path, n_dim0=4, n_dim1=3, n_wl=5, n_pixels_override=10)
        with pytest.raises(ValueError, match="pixel"):
            read_mat_map_data(str(path))

    def test_imagesize_wrong_length_raises(self, tmp_path):
        """A 1-D line scan or 3-D volume (imagesize with != 2 entries)
        is explicitly out of scope and must say so, not be misread as a
        2-D map."""
        path = tmp_path / 'map.mat'
        empty_axisscale = np.empty((2, 2), dtype=object)
        empty_axisscale[:] = [[np.empty((0, 0)), ''], [np.empty((0, 0)), '']]
        scipy.io.savemat(str(path), {'thing': {
            'imagesize': np.array([[4, 3, 2]], dtype=np.uint8),
            'data': np.zeros((24, 5), dtype=np.float32),
            'axisscale': empty_axisscale,
        }})
        with pytest.raises(ValueError, match="2-D"):
            read_mat_map_data(str(path))

    def test_x_axis_length_mismatch_raises(self, tmp_path):
        path = tmp_path / 'map.mat'
        axisscale = np.empty((2, 2), dtype=object)
        axisscale[0, 0] = np.empty((0, 0))
        axisscale[0, 1] = ''
        axisscale[1, 0] = np.array([[1.0, 2.0, 3.0]])   # only 3, data has 5
        axisscale[1, 1] = 'nm'
        scipy.io.savemat(str(path), {'thing': {
            'imagesize': np.array([[2, 2]], dtype=np.uint8),
            'data': np.zeros((4, 5), dtype=np.float32),
            'axisscale': axisscale,
        }})
        with pytest.raises(ValueError, match="x-axis"):
            read_mat_map_data(str(path))


class TestUnitLabelDecoding:
    """
    scipy's MATLAB char-array decoder loses the specific UTF-16 code
    unit U+00B5 ('µ', MICRO SIGN) that WITec's spatial pixel-size unit
    is written with, returning U+FFFD (replacement character) + 'm'
    instead — confirmed by reading a real export's raw bytes directly
    (see _axis_unit_label's docstring). This is corrected back to 'µm'
    since that's the only unit this field is ever populated with; every
    other label passes through unchanged.
    """

    def test_fffd_m_normalised_to_micrometre(self):
        assert _axis_unit_label('\ufffdm') == 'µm'

    def test_correctly_decoded_label_passes_through(self):
        assert _axis_unit_label('rel. 1/cm') == 'rel. 1/cm'

    def test_empty_label_passes_through(self):
        assert _axis_unit_label('') == ''

    def test_array_wrapped_label_still_handled(self):
        import numpy as np
        assert _axis_unit_label(np.array(['\ufffdm'])) == 'µm'


# ---------------------------------------------------------------------------
# Integration with SpectrumManager (the real import path the app uses)
# ---------------------------------------------------------------------------

class TestSpectrumManagerIntegration:

    def test_extension_is_recognised(self):
        assert '.mat' in SpectrumManager.SUPPORTED_EXTENSIONS

    def test_full_import_pipeline(self, tmp_path):
        path = tmp_path / 'sample.mat'
        _write_synthetic_map(path, n_dim0=4, n_dim1=3, n_wl=5)

        mgr = SpectrumManager()
        mgr.load_spectrum_from_file(str(path))

        assert len(mgr.spectra) == 12
        for spectrum in mgr.spectra.values():
            # Application-wide ascending-x invariant (enforced centrally
            # in load_spectrum_from_file for every format) must hold here
            # too.
            assert np.all(np.diff(spectrum.x_scale) >= 0)
            assert 'unique_id' in spectrum.metadata
            assert spectrum.metadata['import_parameters']['map_n_cols'] == 4
            assert spectrum.metadata['import_parameters']['map_n_rows'] == 3
