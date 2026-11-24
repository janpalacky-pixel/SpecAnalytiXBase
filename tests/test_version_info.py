"""tools/version_info.py: the name and version inside SpecAnalytiXBase.exe
(Properties > Details), which Windows' Smart App Control and code signing
need. The 1.7.0 .exe had none (FileVersion 0.0.0.0, no ProductName)."""
import os
import runpy

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tool():
    """Loaded when a test runs, not when the file is collected: the installed
    version has no tools/ (these tests are skipped there, SOURCE_FILE_CHECKS)."""
    return runpy.run_path(os.path.join(ROOT, 'tools', 'version_info.py'))


def test_the_version_is_the_programs_own():
    from src.version import __version__
    assert tool()['program_version']() == __version__


@pytest.mark.parametrize('version, numbers', [
    ('1.7.0', (1, 7, 0, 0)), ('2.0', (2, 0, 0, 0)), ('1.7.12.3', (1, 7, 12, 3)),
    ('1.8.0.dev1', (1, 8, 0, 1)), ('1.8.0-beta', (1, 8, 0, 0))])
def test_four_numbers(version, numbers):
    assert tool()['four_numbers'](version) == numbers


def test_every_name_is_the_programs_name_and_both_versions_agree():
    """SignPath: every product name attribute is the project's name, and the
    versions are the same."""
    text = tool()['text']('1.7.0')
    for key in ('FileDescription', 'InternalName', 'ProductName'):
        assert f"StringStruct('{key}', 'SpecAnalytiXBase')" in text
    assert "StringStruct('OriginalFilename', 'SpecAnalytiXBase.exe')" in text
    assert "StringStruct('FileVersion', '1.7.0')" in text
    assert "StringStruct('ProductVersion', '1.7.0')" in text
    assert 'filevers=(1, 7, 0, 0), prodvers=(1, 7, 0, 0)' in text


def test_pyinstaller_reads_it(tmp_path):
    try:  # PyInstaller's Windows part (the builds run on Windows)
        from PyInstaller.utils.win32 import versioninfo
    except ImportError:
        pytest.skip('PyInstaller (Windows) is not installed')
    path = tmp_path / 'version_info.txt'
    path.write_text(tool()['text']('1.7.0'), encoding='utf-8')
    info = versioninfo.load_version_info_from_text_file(str(path))
    assert info.ffi.fileVersionMS == (1 << 16) | 7
    assert 'SpecAnalytiXBase' in str(info)
