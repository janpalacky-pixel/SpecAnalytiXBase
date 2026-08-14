# tests/conftest.py
#
# Shared fixtures available to all test files automatically.
# pytest loads this file before running any tests.

import numpy as np
import pytest
import os
import tempfile


# ---------------------------------------------------------------------------
# Basic data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_spectrum():
    """A single well-formed spectrum dict."""
    return {
        'label': 'test : 0001',
        'x_scale': np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
        'y_scale': np.array([1.5, 2.5, 3.5, 2.0, 1.0]),
        'metadata': {'file_path': 'test.txt', 'valid_points': 5},
    }


@pytest.fixture
def three_spectra():
    """Three spectra sharing the same x-scale."""
    x = np.linspace(100.0, 500.0, 20)
    return [
        {
            'label': f'test : 000{i}',
            'x_scale': x.copy(),
            'y_scale': np.random.rand(20) * (i + 1),
            'metadata': {'file_path': 'test.txt'},
        }
        for i in range(1, 4)
    ]


@pytest.fixture
def spectra_different_scales():
    """Two spectra with different x-scales (for interlaced save tests)."""
    return [
        {
            'label': 'spec_A',
            'x_scale': np.linspace(100.0, 500.0, 10),
            'y_scale': np.random.rand(10),
            'metadata': {},
        },
        {
            'label': 'spec_B',
            'x_scale': np.linspace(200.0, 800.0, 15),
            'y_scale': np.random.rand(15),
            'metadata': {},
        },
    ]


# ---------------------------------------------------------------------------
# File fixtures — temporary files that are cleaned up after each test
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_txt(tmp_path):
    """Return a path to a temporary .txt file (not yet created)."""
    return str(tmp_path / 'test_spectra.txt')


@pytest.fixture
def tmp_xlsx(tmp_path):
    """Return a path to a temporary .xlsx file (not yet created)."""
    return str(tmp_path / 'test_spectra.xlsx')


@pytest.fixture
def tmp_snapx(tmp_path):
    """Return a path to a temporary .snapx file (not yet created)."""
    return str(tmp_path / 'test_snapshot.snapx')


# ---------------------------------------------------------------------------
# Pre-built sample text file fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tab_dot_file(tmp_path):
    """
    A tab-separated, dot-decimal file with header.
    Layout: x_scale | spec_A | spec_B | spec_C
    """
    content = (
        "x_scale\tspec_A\tspec_B\tspec_C\n"
        "100.0\t1.23\t4.56\t7.89\n"
        "200.0\t2.34\t5.67\t8.90\n"
        "300.0\t3.45\t6.78\t9.01\n"
        "400.0\t4.56\t7.89\t0.12\n"
        "500.0\t5.67\t8.90\t1.23\n"
    )
    path = tmp_path / 'tab_dot.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def semicolon_comma_file(tmp_path):
    """
    A semicolon-separated, comma-decimal file with header.
    Simulates European locale export.
    """
    content = (
        "x_scale;spec_A;spec_B\n"
        "100,0;1,23;4,56\n"
        "200,0;2,34;5,67\n"
        "300,0;3,45;6,78\n"
    )
    path = tmp_path / 'semi_comma.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def no_header_file(tmp_path):
    """Tab-separated, dot-decimal file WITHOUT a header row."""
    content = (
        "100.0\t1.23\t4.56\n"
        "200.0\t2.34\t5.67\n"
        "300.0\t3.45\t6.78\n"
    )
    path = tmp_path / 'no_header.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)


@pytest.fixture
def single_spectrum_file(tmp_path):
    """File with exactly one spectrum (2 columns: x and y)."""
    content = (
        "x_scale\tintensity\n"
        "100.0\t10.5\n"
        "200.0\t20.3\n"
        "300.0\t15.7\n"
    )
    path = tmp_path / 'single.txt'
    path.write_text(content, encoding='utf-8')
    return str(path)
