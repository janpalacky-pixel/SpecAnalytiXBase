# tests/test_header_detection.py
#
# Tests for _detect_header in table_data_converter.py

import pytest
from src.modules.data_io.table_data_converter import _detect_header


class TestHeaderDetection:
    def test_text_header_detected(self):
        lines = [
            "x_scale\tspec_A\tspec_B\tspec_C",
            "100.0\t1.23\t4.56\t7.89",
            "200.0\t2.34\t5.67\t8.90",
        ]
        assert _detect_header(lines, '\t', '.') is True

    def test_numeric_first_row_no_header(self):
        lines = [
            "100.0\t1.23\t4.56",
            "200.0\t2.34\t5.67",
            "300.0\t3.45\t6.78",
        ]
        assert _detect_header(lines, '\t', '.') is False

    def test_partial_text_header(self):
        """First row has some text and some numbers — text majority → header."""
        lines = [
            "wavenumber\tintensity\tbackground\t123.0",
            "100.0\t1.23\t0.5\t0.1",
        ]
        assert _detect_header(lines, '\t', '.') is True

    def test_european_comma_decimal_no_header(self):
        lines = [
            "100,0;1,23;4,56",
            "200,0;2,34;5,67",
        ]
        assert _detect_header(lines, ';', ',') is False

    def test_european_comma_decimal_with_header(self):
        lines = [
            "x_scale;spec_A;spec_B",
            "100,0;1,23;4,56",
            "200,0;2,34;5,67",
        ]
        assert _detect_header(lines, ';', ',') is True

    def test_empty_lines(self):
        assert _detect_header([], '\t', '.') is False

    def test_single_line_numeric(self):
        assert _detect_header(["100.0\t1.23"], '\t', '.') is False

    def test_single_line_text(self):
        assert _detect_header(["x_scale\tintensity"], '\t', '.') is True

    def test_scientific_notation_no_header(self):
        """Scientific notation values must be recognised as numeric."""
        lines = [
            "2.000e+2\t-1.05e-5\t7.29e-4",
            "2.005e+2\t2.14e-4\t6.09e-5",
        ]
        assert _detect_header(lines, '\t', '.') is False

    def test_scientific_comma_decimal_no_header(self):
        lines = [
            "2,000e+2\t-1,05e-5\t7,29e-4",
            "2,005e+2\t2,14e-4\t6,09e-5",
        ]
        assert _detect_header(lines, '\t', ',') is False
