"""Guards for installer.iss.

Regression: v1.4.0 installed over v1.3.0 (same AppId, same folder) and crashed at
startup with "module 'pyarrow' has no attribute '__version__'". v1.3.0 had shipped a
bare _internal\\pyarrow folder; v1.4.0 doesn't ship pyarrow, but Inno Setup never
deletes files it isn't installing, so the stale folder stayed on sys.path, got imported
as an empty namespace package, and broke pandas. The installer must therefore clear the
old bundled-library folder before copying the new files.
"""

import re
from pathlib import Path

ISS = (Path(__file__).resolve().parent.parent / "installer.iss").read_text(encoding="utf-8")


def _section(name):
    m = re.search(rf"^\[{name}\]\s*$(.*?)(?=^\[|\Z)", ISS, re.S | re.M)
    return m.group(1) if m else None


def test_install_delete_section_clears_old_internal_folder():
    body = _section("InstallDelete")
    assert body is not None, "installer.iss needs an [InstallDelete] section"
    entries = [l for l in body.splitlines() if l.strip() and not l.strip().startswith(";")]
    assert any(
        "filesandordirs" in e and re.search(r'Name:\s*"\{app\}\\_internal"', e) for e in entries
    ), "[InstallDelete] must remove {app}\\_internal so stale libraries from older versions don't survive an upgrade"

