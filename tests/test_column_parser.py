# tests/test_column_parser.py
#
# Tests for _parse_column_data — the core spectrum builder.
# NOTE: _parse_column_data reads file timestamps from the filepath,
# so all calls must use a real file that exists on disk.

import re
import time
import pytest
import numpy as np
from src.modules.data_io.table_data_converter import _parse_column_data


def make_lines(rows, delimiter='\t'):
    """Helper: convert a list of lists to text lines."""
    return [delimiter.join(str(v) for v in row) for row in rows]


def parse(lines, tmp_path, delimiter='\t', decimal='.', header=False, padding=4,
          filename='test.txt'):
    """Helper: write lines to a real temp file and call _parse_column_data."""
    p = tmp_path / filename
    p.write_text('\n'.join(lines), encoding='utf-8')
    return _parse_column_data(lines, str(p), delimiter, decimal, header, padding)


class TestSpectrumCount:
    def test_three_spectra(self, tmp_path):
        lines = make_lines([
            [100.0, 1.0, 2.0, 3.0],
            [200.0, 4.0, 5.0, 6.0],
            [300.0, 7.0, 8.0, 9.0],
        ])
        spectra = parse(lines, tmp_path)
        assert len(spectra) == 3

    def test_single_spectrum(self, tmp_path):
        lines = make_lines([[100.0, 1.0], [200.0, 2.0]])
        spectra = parse(lines, tmp_path)
        assert len(spectra) == 1

    def test_nan_column_skipped(self, tmp_path):
        """A completely NaN y-column must be skipped silently."""
        lines = [
            "100.0\t1.0\t\t3.0",
            "200.0\t2.0\t\t4.0",
            "300.0\t3.0\t\t5.0",
        ]
        spectra = parse(lines, tmp_path)
        assert len(spectra) == 2

    def test_spectrum_counter_no_gaps(self, tmp_path):
        """When a NaN column is skipped, labels must be 0001, 0002 (no gaps)."""
        lines = ["100.0\t1.0\t\t3.0", "200.0\t2.0\t\t4.0"]
        spectra = parse(lines, tmp_path)
        labels = [sp['label'] for sp in spectra]
        assert '0001' in labels[0]
        assert '0002' in labels[1]
        assert '0003' not in ''.join(labels)


class TestLabelHandling:
    def test_labels_from_header(self, tmp_path):
        lines = [
            "x_scale\tspec_A\tspec_B",
            "100.0\t1.0\t2.0",
            "200.0\t3.0\t4.0",
        ]
        spectra = parse(lines, tmp_path, header=True, filename='myfile.txt')
        labels = [sp['label'] for sp in spectra]
        assert any('spec_A' in l for l in labels)
        assert any('spec_B' in l for l in labels)

    def test_auto_labels_without_header(self, tmp_path):
        lines = ["100.0\t1.0\t2.0", "200.0\t3.0\t4.0"]
        spectra = parse(lines, tmp_path, filename='myfile.txt')
        labels = [sp['label'] for sp in spectra]
        assert all('myfile' in l for l in labels)

    def test_single_spectrum_label_is_basename(self, tmp_path):
        """Single-spectrum file → label is just the base filename."""
        lines = ["100.0\t1.0", "200.0\t2.0"]
        spectra = parse(lines, tmp_path, filename='myfile.txt')
        assert spectra[0]['label'] == 'myfile'

    def test_zero_padding_applied(self, tmp_path):
        row = [100.0] + [float(i) for i in range(1, 6)]
        lines = make_lines([row])
        spectra = parse(lines, tmp_path, padding=4)
        for sp in spectra:
            assert re.search(r'\d{4}', sp['label']), (
                f"No zero-padded number in '{sp['label']}'"
            )


class TestDataValues:
    def test_x_scale_correct(self, tmp_path):
        lines = make_lines([
            [100.0, 1.0, 2.0],
            [200.0, 3.0, 4.0],
            [300.0, 5.0, 6.0],
        ])
        spectra = parse(lines, tmp_path)
        np.testing.assert_allclose(spectra[0]['x_scale'], [100.0, 200.0, 300.0])
        np.testing.assert_allclose(spectra[1]['x_scale'], [100.0, 200.0, 300.0])

    def test_y_scale_correct(self, tmp_path):
        lines = make_lines([
            [100.0, 1.0, 10.0],
            [200.0, 2.0, 20.0],
            [300.0, 3.0, 30.0],
        ])
        spectra = parse(lines, tmp_path)
        np.testing.assert_allclose(spectra[0]['y_scale'], [1.0, 2.0, 3.0])
        np.testing.assert_allclose(spectra[1]['y_scale'], [10.0, 20.0, 30.0])

    def test_comma_decimal_values(self, tmp_path):
        lines = ["100,0;1,5;2,5", "200,0;3,5;4,5", "300,0;5,5;6,5"]
        spectra = parse(lines, tmp_path, delimiter=';', decimal=',')
        assert len(spectra) == 2
        np.testing.assert_allclose(spectra[0]['x_scale'], [100.0, 200.0, 300.0])
        np.testing.assert_allclose(spectra[0]['y_scale'], [1.5, 3.5, 5.5])

    def test_metadata_contains_file_path(self, tmp_path):
        p = tmp_path / 'myfile.txt'
        lines = make_lines([[100.0, 1.0], [200.0, 2.0]])
        p.write_text('\n'.join(lines))
        spectra = _parse_column_data(lines, str(p), '\t', '.', False, 4)
        assert spectra[0]['metadata']['file_path'] == str(p)

    def test_valid_points_count(self, tmp_path):
        lines = make_lines([[100.0, 1.0], [200.0, 2.0], [300.0, 3.0]])
        spectra = parse(lines, tmp_path)
        assert spectra[0]['metadata']['valid_points'] == 3


class TestEdgeCases:
    def test_raises_on_no_data(self, tmp_path):
        with pytest.raises(ValueError):
            _parse_column_data([], str(tmp_path / 'empty.txt'), '\t', '.', False, 4)

    def test_raises_on_single_column(self, tmp_path):
        lines = ["100.0", "200.0", "300.0"]
        p = tmp_path / 'single.txt'
        p.write_text('\n'.join(lines))
        with pytest.raises(ValueError):
            _parse_column_data(lines, str(p), '\t', '.', False, 4)

    def test_large_file_performance(self, tmp_path):
        """2000 rows × 26 spectra should complete in reasonable time."""
        rows = [[float(i)] + [float(i * j * 0.1) for j in range(1, 27)]
                for i in range(1, 2001)]
        lines = make_lines(rows)
        t0 = time.time()
        spectra = parse(lines, tmp_path, filename='large.txt')
        elapsed = time.time() - t0
        assert len(spectra) == 26
        assert elapsed < 5.0, f"Parsing took {elapsed:.1f}s — too slow"
