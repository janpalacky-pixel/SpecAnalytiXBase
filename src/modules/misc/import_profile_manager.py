# src/modules/misc/import_profile_manager.py
#
# Named Import Profiles.
#
# Persists a full Import-dialog settings snapshot under a user-chosen
# name, so it can be reapplied later — to a different file, and unlike
# the in-dialog "Apply to All Other Files" action, in a *different
# application session entirely*. Useful for a recurring instrument
# export format you import repeatedly across projects.
#
# Storage: a single JSON file in the same per-user app-data location the
# app already uses for logs (see app_logger._log_dir()) — same reasoning
# applies here: persistent, writable, and consistent with where the rest
# of the app's on-disk state already lives, with no separate
# configuration needed.

import os
import sys

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)
from src.modules.utils.json_store import read_json_store, write_json_atomic


def _profiles_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.specanalytixbase")
    return os.path.join(base, "SpecAnalytiXBase")


def _profiles_file() -> str:
    return os.path.join(_profiles_dir(), "import_profiles.json")


class ImportProfileManager:
    """
    Manages named Import-dialog settings profiles, persisted to a single
    JSON file so they survive across application sessions — not just
    within one Import dialog instance, unlike per-file settings or
    "Apply to All Other Files".

    A profile is a plain settings dict — the same shape
    ImportDialog.get_settings() returns — stored verbatim under a name.
    Column-index settings (label_column, x_scale_column, exclude_columns)
    and sheet_name carry the same caveat as "Apply to All Other Files":
    they're copied as-is, which is exactly right when reapplied to a
    file with the same layout/workbook structure the profile was saved
    from, and falls back gracefully (Auto, or a clear per-file import
    error) otherwise — see import_dialog.py's _apply_profile and
    import_help.py for the full explanation.
    """

    def __init__(self):
        self._path = _profiles_file()

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _load_all(self) -> dict:
        # An unreadable file is copied aside before being treated as empty,
        # so the next save cannot silently wipe every saved item (see
        # json_store.read_json_store).
        return read_json_store(self._path, 'import profiles')

    def _save_all(self, items: dict) -> None:
        try:
            write_json_atomic(self._path, items)
        except OSError as exc:
            raise RuntimeError(f"Could not save import profile: {exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_profiles(self) -> list:
        """Return saved profile names, alphabetically."""
        return sorted(self._load_all().keys())

    def save_profile(self, name: str, settings: dict) -> None:
        """Save (or silently overwrite) a named profile."""
        name = name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty.")
        profiles = self._load_all()
        profiles[name] = dict(settings)
        self._save_all(profiles)
        logger.info("Saved import profile %r", name)

    def load_profile(self, name: str) -> dict:
        """Return a copy of the settings dict for a saved profile."""
        profiles = self._load_all()
        if name not in profiles:
            raise KeyError(f"No import profile named {name!r}")
        return dict(profiles[name])

    def delete_profile(self, name: str) -> None:
        """Remove a saved profile, if present. No-op if it doesn't exist."""
        profiles = self._load_all()
        if name in profiles:
            del profiles[name]
            self._save_all(profiles)
            logger.info("Deleted import profile %r", name)
