# tests/test_decimal_detection.py
#
# Tests for _detect_decimal_separator and _convert_to_float.

import pytest
import numpy as np
from src.modules.data_io.table_data_converter import (
    _detect_decimal_separator,
    _convert_to_float,
    _safe_convert,
)


class TestDecimalDetection:
    def test_dot_decimal_tab(self):
        lines = ["100.0\t1.23\t4.56", "200.0\t2.34\t5.67"]
        assert _detect_decimal_separator(lines, '\t') == '.'

    def test_comma_decimal_semicolon(self):
        lines = ["100,0;1,23;4,56", "200,0;2,34;5,67"]
        assert _detect_decimal_separator(lines, ';') == ','

    def test_dot_decimal_comma_delimiter(self):
        lines = ["100.0,1.23,4.56", "200.0,2.34,5.67"]
        assert _detect_decimal_separator(lines, ',') == '.'

    def test_scientific_notation_dot(self):
        lines = [
            "2.000e+2\t-1.05e-5\t7.29e-4",
            "2.005e+2\t2.14e-4\t6.09e-5",
        ]
        assert _detect_decimal_separator(lines, '\t') == '.'

    def test_scientific_notation_comma(self):
        lines = [
            "2,000e+2\t-1,05e-5\t7,29e-4",
            "2,005e+2\t2,14e-4\t6,09e-5",
        ]
        assert _detect_decimal_separator(lines, '\t') == ','

    def test_mixed_favours_majority(self):
        """More comma-decimals than dot-decimals → comma chosen."""
        lines = [
            "1,5;2,3;3,7",
            "4,1;5,9;6,2",
            "7,8;8,4;9.0",  # one dot
        ]
        assert _detect_decimal_separator(lines, ';') == ','


class TestConvertToFloat:
    def test_dot_decimal(self):
        assert _convert_to_float("3.14", '.') == pytest.approx(3.14)

    def test_comma_decimal(self):
        assert _convert_to_float("3,14", ',') == pytest.approx(3.14)

    def test_scientific_dot(self):
        assert _convert_to_float("1.5e3", '.') == pytest.approx(1500.0)

    def test_scientific_comma(self):
        assert _convert_to_float("1,5e3", ',') == pytest.approx(1500.0)

    def test_scientific_with_plus(self):
        assert _convert_to_float("1,5E+3", ',') == pytest.approx(1500.0)

    def test_scientific_with_minus(self):
        assert _convert_to_float("1,5e-3", ',') == pytest.approx(0.0015)

    def test_negative_value(self):
        assert _convert_to_float("-2,5", ',') == pytest.approx(-2.5)

    def test_integer_value(self):
        assert _convert_to_float("42", '.') == pytest.approx(42.0)

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            _convert_to_float("x_scale", '.')

    def test_empty_string_returns_nan(self):
        result = _convert_to_float("", '.')
        assert np.isnan(result)

    def test_large_scientific(self):
        assert _convert_to_float("2,000000000000000e+2", ',') == pytest.approx(200.0)

    def test_small_scientific(self):
        assert _convert_to_float("-1,050000000000000e-5", ',') == pytest.approx(-1.05e-5)


class TestSafeConvert:
    def test_valid_returns_float(self):
        assert _safe_convert("1.5", '.') == pytest.approx(1.5)

    def test_invalid_returns_nan(self):
        assert np.isnan(_safe_convert("not_a_number", '.'))

    def test_empty_returns_nan(self):
        assert np.isnan(_safe_convert("", '.'))

    def test_comma_decimal(self):
        assert _safe_convert("1,5", ',') == pytest.approx(1.5)
