"""The name and version inside SpecAnalytiXBase.exe (Properties > Details in
Windows): writes build/version_info.txt for PyInstaller's --version-file,
from src/version.py, so the .exe always carries the program's own version.

Windows' Smart App Control and code signing (SignPath) need it: an .exe
without a product name and version ("FileVersion 0.0.0.0", empty
ProductName) is what Windows' log showed for the blocked 1.7.0. Run from the
project folder before PyInstaller (BuildInstaller.bat and the GitHub builds
do):
    python tools/version_info.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'version_info.txt')
NAME = 'SpecAnalytiXBase'
COMPANY = 'Institute of Biophysics of the Czech Academy of Sciences'
COPYRIGHT = ('Copyright (C) 2026 Institute of Biophysics of the Czech Academy of '
             'Sciences, v. v. i. - GNU GPL v3')


def program_version():
    """'1.7.0' from src/version.py (read as text: nothing is imported)."""
    with open(os.path.join(ROOT, 'src', 'version.py'), encoding='utf-8') as f:
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
    if not m:
        raise SystemExit('src/version.py: no __version__ found')
    return m.group(1)


def four_numbers(version):
    """'1.7.0' -> (1, 7, 0, 0); text after the numbers (e.g. '1.8.0.dev1') is left out."""
    nums = [int(n) for n in re.findall(r'\d+', version.split('-')[0])][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def text(version):
    v4 = four_numbers(version)
    strings = [('CompanyName', COMPANY), ('FileDescription', NAME),
               ('FileVersion', version), ('InternalName', NAME),
               ('LegalCopyright', COPYRIGHT), ('OriginalFilename', NAME + '.exe'),
               ('ProductName', NAME), ('ProductVersion', version)]
    table = ',\n        '.join(f'StringStruct({k!r}, {v!r})' for k, v in strings)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v4}, prodvers={v4}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
        {table}])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main():
    version = program_version()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(text(version))
    print(f'{OUT}: {NAME} {version}')


if __name__ == '__main__':
    sys.exit(main())
