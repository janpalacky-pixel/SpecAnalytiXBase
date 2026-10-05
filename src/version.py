# src/version.py
"""
Single place the running application reads its own version from (shown in
Help > About). It must always equal MyAppVersion in installer.iss, which
names the installer file and is checked against the git tag by the Release
build workflow -- tests/test_about_info.py fails if the two ever differ, so
bump both together when cutting a release.
"""

__version__ = "1.4.1"
