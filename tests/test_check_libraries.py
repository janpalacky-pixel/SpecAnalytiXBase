"""tools/check_libraries.py: are this Python's libraries those of the GitHub build?"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'check_libraries', os.path.join(ROOT, 'tools', 'check_libraries.py'))
cl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)

REQ = [('numpy', '2.5.3'), ('matplotlib', '3.11.2')]


def test_reads_the_real_requirements_and_the_github_python():
    req = dict(cl.read_requirements())
    assert 'matplotlib' in req and 'numpy' in req and 'PyQt5' in req
    assert all(v[0].isdigit() for v in req.values())
    assert cl.github_python() and cl.github_python().startswith('3.')


def test_comments_and_blank_lines_are_ignored(tmp_path):
    p = tmp_path / 'requirements.txt'
    p.write_text('# numpy==1.0\n\nscipy==1.18.1   # comment\n  # x==2\nopenpyxl==3.1.5\n',
                 encoding='utf-8')
    assert cl.read_requirements(str(p)) == [('scipy', '1.18.1'), ('openpyxl', '3.1.5')]


def test_all_the_same_says_libraries_ok():
    lines, bad = cl.check(REQ, installed=dict(REQ).get,
                          python_version='3.12.10', wanted_python='3.12')
    assert bad == 0
    assert lines[-1] == 'Libraries OK: Python 3.12 and all 2 libraries as in the GitHub build.'
    assert all(line.rstrip().endswith('OK') for line in lines[:-1])


def test_a_different_or_missing_library_gives_a_warning():
    installed = {'numpy': '2.5.3'}           # matplotlib missing
    lines, bad = cl.check(REQ, installed=installed.get,
                          python_version='3.12.1', wanted_python='3.12')
    assert bad == 1
    assert any('matplotlib' in line and 'NOT INSTALLED' in line for line in lines)
    assert any(line.startswith('WARNING - LIBRARIES DIFFER') for line in lines)
    lines, bad = cl.check(REQ, installed={'numpy': '2.4.0', 'matplotlib': '3.11.2'}.get,
                          python_version='3.12.1', wanted_python='3.12')
    assert bad == 1
    assert any('numpy' in line and 'DIFFERENT - requirements.txt: 2.5.3' in line for line in lines)


def test_another_python_version_gives_a_warning():
    lines, bad = cl.check(REQ, installed=dict(REQ).get,
                          python_version='3.10.12', wanted_python='3.12')
    assert bad == 1
    assert 'DIFFERENT - GitHub build: 3.12' in lines[0]
    # 3.1 is not 3.12, and 3.12 is not 3.1
    assert cl.check([], python_version='3.12.0', wanted_python='3.1')[1] == 1
