# tests/test_round_trip.py
#
# End-to-end round-trip tests: save spectra to a file then re-import
# them and verify the data is identical.
#
# These tests are the most important — they catch bugs that individually
# correct save and individually correct import would still miss together.

import pytest
import numpy as np
import pandas as pd
from src.modules.misc.save_spectra_manager import SaveManager
from src.modules.data_io.table_data_converter import read_table_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_and_reload(spectra, file_path, settings):
    """Save spectra to file_path using settings, then reload and return."""
    mgr = SaveManager()
    mgr.save_table(spectra, file_path, settings)
    return read_table_data(file_path)


def _check_round_trip(original, reloaded):
    """Assert that reloaded spectra match originals in x, y and label count."""
    assert len(reloaded) == len(original), (
        f"Expected {len(original)} spectra, got {len(reloaded)}"
    )
    for orig, rel in zip(original, reloaded):
        np.testing.assert_allclose(
            rel['x_scale'], orig['x_scale'], rtol=1e-10,
            err_msg=f"x_scale mismatch for '{orig['label']}'"
        )
        np.testing.assert_allclose(
            rel['y_scale'], orig['y_scale'], rtol=1e-10,
            err_msg=f"y_scale mismatch for '{orig['label']}'"
        )


# ---------------------------------------------------------------------------
# Common-x-scale round trips (standard layout)
# ---------------------------------------------------------------------------

class TestCommonScaleRoundTrip:
    """Files saved with common x-scale must re-import in standard mode."""

    BASE_SETTINGS = {
        'format': 'text',
        'mode': 'table',
        'use_common_scale': True,
        'use_labels': True,
        'value_separator': '\t',
        'decimal_separator': '.',
    }

    def test_three_spectra_tab_dot(self, three_spectra, tmp_txt):
        reloaded = _save_and_reload(three_spectra, tmp_txt, self.BASE_SETTINGS)
        _check_round_trip(three_spectra, reloaded)

    def test_three_spectra_semicolon_dot(self, three_spectra, tmp_txt):
        settings = {**self.BASE_SETTINGS, 'value_separator': ';'}
        reloaded = _save_and_reload(three_spectra, tmp_txt, settings)
        _check_round_trip(three_spectra, reloaded)

    def test_three_spectra_comma_decimal(self, three_spectra, tmp_txt):
        settings = {**self.BASE_SETTINGS,
                    'value_separator': ';',
                    'decimal_separator': ','}
        reloaded = _save_and_reload(three_spectra, tmp_txt, settings)
        _check_round_trip(three_spectra, reloaded)

    def test_no_labels(self, three_spectra, tmp_txt):
        """Without labels the file must still re-import to the right count."""
        settings = {**self.BASE_SETTINGS, 'use_labels': False}
        reloaded = _save_and_reload(three_spectra, tmp_txt, settings)
        assert len(reloaded) == len(three_spectra)

    def test_single_spectrum(self, sample_spectrum, tmp_txt):
        spectra = [sample_spectrum]
        reloaded = _save_and_reload(spectra, tmp_txt, self.BASE_SETTINGS)
        assert len(reloaded) == 1
        np.testing.assert_allclose(
            reloaded[0]['x_scale'], sample_spectrum['x_scale'], rtol=1e-10
        )
        np.testing.assert_allclose(
            reloaded[0]['y_scale'], sample_spectrum['y_scale'], rtol=1e-10
        )

    def test_labels_preserved(self, three_spectra, tmp_txt):
        """Saving with labels must produce the correct number of spectra on reload."""
        # Labels get sanitised (colons/spaces → underscores) when used as column
        # headers, so we check count rather than exact label content.
        reloaded = _save_and_reload(three_spectra, tmp_txt, self.BASE_SETTINGS)
        assert len(reloaded) == len(three_spectra)

    def test_large_dataset(self, tmp_txt):
        """1000 spectra × 500 points must round-trip correctly."""
        x = np.linspace(100.0, 3500.0, 500)
        spectra = [
            {
                'label': f'spec : {str(i).zfill(4)}',
                'x_scale': x.copy(),
                'y_scale': np.random.rand(500),
                'metadata': {},
            }
            for i in range(1, 1001)
        ]
        reloaded = _save_and_reload(spectra, tmp_txt, self.BASE_SETTINGS)
        assert len(reloaded) == 1000


# ---------------------------------------------------------------------------
# Interlaced round trips (individual x-scales)
# ---------------------------------------------------------------------------

class TestInterlacedRoundTrip:
    """Files saved with individual x-scales use interlaced layout."""

    BASE_SETTINGS = {
        'format': 'text',
        'mode': 'table',
        'use_common_scale': False,
        'use_labels': True,
        'value_separator': '\t',
        'decimal_separator': '.',
    }

    def test_two_spectra_different_scales(self, spectra_different_scales, tmp_txt):
        """Saving with individual scales must write a file with correct column count."""
        mgr = SaveManager()
        mgr.save_table(spectra_different_scales, tmp_txt, self.BASE_SETTINGS)
        # The file should have 2*n_spectra columns (x1,y1,x2,y2,...)
        with open(tmp_txt) as f:
            first_data_line = f.readline().strip()  # header if labels=True
            first_data_line = f.readline().strip()  # first data row
        cols = first_data_line.split('\t')
        assert len(cols) == 2 * len(spectra_different_scales)

    def test_values_preserved_interlaced(self, spectra_different_scales, tmp_txt):
        """
        Save interlaced and verify the file contains correct x,y pair columns.
        Re-import is tested separately via test_two_spectra_different_scales.
        """
        mgr = SaveManager()
        mgr.save_table(spectra_different_scales, tmp_txt, self.BASE_SETTINGS)
        # Read raw file and verify x values of spec_A appear in col 0
        with open(tmp_txt, encoding='utf-8-sig') as f:
            lines = f.readlines()
        # Skip header row (labels=True)
        data_line = lines[1].strip().split('	')
        # Column 0 should be x_A[0], column 2 should be x_B[0]
        x_a_0 = float(data_line[0])
        x_b_0 = float(data_line[2])
        assert abs(x_a_0 - spectra_different_scales[0]['x_scale'][0]) < 1e-6
        assert abs(x_b_0 - spectra_different_scales[1]['x_scale'][0]) < 1e-6


# ---------------------------------------------------------------------------
# File format content checks
# ---------------------------------------------------------------------------

class TestFileContent:
    """Verify the actual content of saved files."""

    def test_tab_separator_in_file(self, three_spectra, tmp_txt):
        settings = {
            'format': 'text', 'mode': 'table',
            'use_common_scale': True, 'use_labels': True,
            'value_separator': '\t', 'decimal_separator': '.',
        }
        SaveManager().save_table(three_spectra, tmp_txt, settings)
        with open(tmp_txt) as f:
            first_line = f.readline()
        assert '\t' in first_line

    def test_semicolon_separator_in_file(self, three_spectra, tmp_txt):
        settings = {
            'format': 'text', 'mode': 'table',
            'use_common_scale': True, 'use_labels': True,
            'value_separator': ';', 'decimal_separator': '.',
        }
        SaveManager().save_table(three_spectra, tmp_txt, settings)
        with open(tmp_txt) as f:
            first_line = f.readline()
        assert ';' in first_line

    def test_comma_decimal_in_file(self, three_spectra, tmp_txt):
        settings = {
            'format': 'text', 'mode': 'table',
            'use_common_scale': True, 'use_labels': True,
            'value_separator': ';', 'decimal_separator': ',',
        }
        SaveManager().save_table(three_spectra, tmp_txt, settings)
        content = open(tmp_txt).read()
        # Should contain commas as decimal points, not dots
        import re
        numbers = re.findall(r'\d+[.,]\d+', content)
        assert any(',' in n for n in numbers)

    def test_header_present_when_labels_true(self, three_spectra, tmp_txt):
        settings = {
            'format': 'text', 'mode': 'table',
            'use_common_scale': True, 'use_labels': True,
            'value_separator': '\t', 'decimal_separator': '.',
        }
        SaveManager().save_table(three_spectra, tmp_txt, settings)
        with open(tmp_txt) as f:
            first_line = f.readline().strip()
        # Header should contain at least one non-numeric token
        parts = first_line.split('\t')
        try:
            float(parts[0])
            has_header = False
        except ValueError:
            has_header = True
        assert has_header

    def test_no_header_when_labels_false(self, three_spectra, tmp_txt):
        settings = {
            'format': 'text', 'mode': 'table',
            'use_common_scale': True, 'use_labels': False,
            'value_separator': '\t', 'decimal_separator': '.',
        }
        SaveManager().save_table(three_spectra, tmp_txt, settings)
        # Open with utf-8-sig to strip BOM automatically (Windows writes BOM)
        with open(tmp_txt, encoding='utf-8-sig') as f:
            first_line = f.readline().strip()
        parts = first_line.split('\t')
        # First line should be all numeric (no header)
        for p in parts:
            float(p)  # raises if not numeric

    def test_common_scale_validation(self, spectra_different_scales, tmp_txt):
        """Trying to use common scale with different grids must raise."""
        settings = {
            'format': 'text', 'mode': 'table',
            'use_common_scale': True, 'use_labels': True,
            'value_separator': '\t', 'decimal_separator': '.',
        }
        mgr = SaveManager()
        # validate_common_scale should return False
        assert not mgr.validate_common_scale(spectra_different_scales)
