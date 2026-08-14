# tests/test_delimiter_detection.py
#
# Tests for _detect_delimiter in table_data_converter.py
#
# Each test creates a small list of sample lines and checks that the
# correct delimiter is returned.

import pytest
from src.modules.data_io.table_data_converter import _detect_delimiter


class TestTabDelimiter:
    def test_simple_tab(self):
        lines = ["100.0\t1.23\t4.56", "200.0\t2.34\t5.67", "300.0\t3.45\t6.78"]
        assert _detect_delimiter(lines) == '\t'

    def test_tab_with_long_numbers(self):
        """Tab detection must use column count, not character count."""
        lines = [
            "78.0\t107.3933141220203\t49.5569102990826\t34.2227415134877",
            "80.0\t108.2292658206257\t46.0785196022242\t34.6532879712073",
            "82.0\t107.6621204584996\t43.0422558284720\t35.2822239381844",
        ]
        assert _detect_delimiter(lines) == '\t'

    def test_tab_with_header(self):
        lines = ["x_scale\tspec_A\tspec_B", "100.0\t1.23\t4.56", "200.0\t2.34\t5.67"]
        assert _detect_delimiter(lines) == '\t'


class TestSemicolonDelimiter:
    def test_simple_semicolon(self):
        lines = ["100.0;1.23;4.56", "200.0;2.34;5.67"]
        assert _detect_delimiter(lines) == ';'

    def test_semicolon_with_comma_decimal(self):
        """Semicolon delimiter with comma as decimal — comma must NOT be chosen."""
        lines = ["100,0;1,23;4,56", "200,0;2,34;5,67", "300,0;3,45;6,78"]
        result = _detect_delimiter(lines)
        assert result == ';', f"Expected ';' but got '{result}'"

    def test_semicolon_header(self):
        lines = ["x;a;b", "1.0;2.0;3.0", "4.0;5.0;6.0"]
        assert _detect_delimiter(lines) == ';'


class TestCommaDelimiter:
    def test_comma_as_delimiter_with_dot_decimal(self):
        """Comma should be chosen only when it is clearly the column separator."""
        lines = ["100.0,1.23,4.56", "200.0,2.34,5.67", "300.0,3.45,6.78"]
        assert _detect_delimiter(lines) == ','

    def test_comma_NOT_chosen_when_decimal(self):
        """
        File uses comma as decimal separator and semicolon as column separator.
        Comma must not be chosen as delimiter.
        """
        lines = ["100,0;1,23;4,56", "200,0;2,34;5,67"]
        assert _detect_delimiter(lines) == ';'


class TestPipeDelimiter:
    def test_pipe(self):
        lines = ["100.0|1.23|4.56", "200.0|2.34|5.67"]
        assert _detect_delimiter(lines) == '|'


class TestWhitespaceDelimiter:
    def test_space_separated(self):
        lines = ["100.0 1.23 4.56", "200.0 2.34 5.67", "300.0 3.45 6.78"]
        result = _detect_delimiter(lines)
        assert result == r'\s+'

    def test_multiple_spaces(self):
        lines = ["100.0  1.23  4.56", "200.0  2.34  5.67"]
        result = _detect_delimiter(lines)
        assert result == r'\s+'


class TestEdgeCases:
    def test_empty_lines(self):
        """Empty input should not crash."""
        result = _detect_delimiter([])
        assert isinstance(result, str)

    def test_single_column(self):
        """Files with only one column — no delimiter needed."""
        lines = ["100.0", "200.0", "300.0"]
        # Should return something without crashing
        result = _detect_delimiter(lines)
        assert isinstance(result, str)

    def test_consistent_tab_wins_over_comma(self):
        """When both tab and comma appear, tab should win (checked first)."""
        lines = [
            "100.0\t1,234\t4,567",
            "200.0\t2,345\t5,678",
        ]
        assert _detect_delimiter(lines) == '\t'
