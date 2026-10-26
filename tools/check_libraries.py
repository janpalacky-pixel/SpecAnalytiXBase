"""Are the libraries of this Python the ones the GitHub build uses?

The GitHub build installs exactly the versions in requirements.txt, on the
Python version named in .github/workflows/nightly-build.yml. This compares
them, one by one, with what is installed in the Python that runs this script,
and prints one line per library and a summary:

    Libraries OK: Python 3.12 and all 7 libraries as in the GitHub build.
or
    WARNING - LIBRARIES DIFFER from the GitHub build: ...

Used at the start of tools/run_tests_windows.bat and
tools/make_all_help_pictures.bat. It only reports; it never installs anything.
Run by hand:  python tools/check_libraries.py
"""
import os
import re
import sys
from importlib import metadata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(ROOT, 'requirements.txt')
WORKFLOW = os.path.join(ROOT, '.github', 'workflows', 'nightly-build.yml')


def read_requirements(path=REQUIREMENTS):
    """[(name, version)] of the lines 'name==version' (comments ignored)."""
    pairs = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            m = re.match(r'^([A-Za-z0-9_.\-]+)\s*==\s*([^\s;]+)$', line)
            if m:
                pairs.append((m.group(1), m.group(2)))
    return pairs


def github_python(path=WORKFLOW):
    """The Python version of the GitHub build, e.g. '3.12' (None if not found)."""
    try:
        with open(path, encoding='utf-8') as f:
            m = re.search(r"python-version:\s*['\"]?([0-9.]+)", f.read())
    except OSError:
        return None
    return m.group(1) if m else None


def installed_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check(requirements, installed=installed_version, python_version=None, wanted_python=None):
    """(lines, number of differences)."""
    if python_version is None:
        python_version = '%d.%d.%d' % sys.version_info[:3]
    lines, bad = [], 0
    if wanted_python:
        same = (python_version + '.').startswith(wanted_python + '.')
        bad += not same
        lines.append('  %-14s %-10s %s' % ('Python', python_version,
                     'OK' if same else 'DIFFERENT - GitHub build: %s' % wanted_python))
    for name, wanted in requirements:
        have = installed(name)
        if have == wanted:
            state = 'OK'
        elif have is None:
            state, have = 'NOT INSTALLED - requirements.txt: %s' % wanted, '-'
            bad += 1
        else:
            state = 'DIFFERENT - requirements.txt: %s' % wanted
            bad += 1
        lines.append('  %-14s %-10s %s' % (name, have, state))
    n = len(requirements)
    if bad == 0:
        what = ('Python %s and all %d libraries' % (wanted_python, n) if wanted_python
                else 'all %d libraries' % n)
        lines.append('Libraries OK: %s as in the GitHub build.' % what)
    else:
        lines.append('WARNING - LIBRARIES DIFFER from the GitHub build: %d of %d differ '
                     '(see above); results may differ from GitHub.' % (bad, n + bool(wanted_python)))
        lines.append('To fix: "%s" -m pip install -r requirements.txt' % sys.executable)
    return lines, bad


def main():
    print('Python used: %s' % sys.executable)
    print('Compared with requirements.txt and the GitHub build (.github/workflows/nightly-build.yml):')
    lines, _ = check(read_requirements(), wanted_python=github_python())
    print('\n'.join(lines))
    print()


if __name__ == '__main__':
    main()
