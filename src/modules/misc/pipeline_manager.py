# src/modules/misc/pipeline_manager.py
#
# Named Batch Pipelines.
#
# Persists a named, ordered sequence of processing-operation steps (each
# an {'operation': <type string>, 'settings': <settings dict>} pair) so
# it can be replayed later — on a different spectra selection, and in a
# different application session entirely. This is the reusable, permanent
# counterpart to "just repeat what I did to this one spectrum": a
# pipeline is captured once (see batch_pipeline_controller.py's
# "Save as Pipeline..." flow, seeded from the session's Operations
# History) and can then be run on any selection, indefinitely.
#
# Storage: a single JSON file in the same per-user app-data location the
# app already uses for logs and Import Profiles (see
# app_logger._log_dir() / import_profile_manager.py) — same reasoning
# applies here: persistent, writable, and consistent with where the rest
# of the app's on-disk state already lives, with no separate
# configuration needed. Deliberately mirrors ImportProfileManager's
# structure (list/save/load/delete) rather than inventing a new pattern.

import os
import sys
import json
from datetime import datetime

from src.modules.utils.app_logger import get_logger
logger = get_logger(__name__)


def _pipelines_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.specanalytixbase")
    return os.path.join(base, "SpecAnalytiXBase")


def _pipelines_file() -> str:
    return os.path.join(_pipelines_dir(), "batch_pipelines.json")


class PipelineManager:
    """
    Manages named Batch Pipelines, persisted to a single JSON file so
    they survive across application sessions.

    A pipeline is stored as:
        {'steps': [{'operation': str, 'settings': dict}, ...],
         'created': <ISO timestamp>}

    'operation' is one of BatchPipelineManager.ELIGIBLE_OPERATIONS'
    keys — the exact internal operation-type string used everywhere else
    in the app (e.g. 'SNIP Baseline', 'Normalization') — and 'settings'
    is the same settings dict shape each operation's manager already
    accepts, stored verbatim.
    """

    def __init__(self):
        self._path = _pipelines_file()

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _load_all(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                logger.warning("Batch pipelines file is not a JSON object — ignoring its contents.")
                return {}
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read batch pipelines file (%s): %s", self._path, exc)
            return {}

    def _save_all(self, pipelines: dict) -> None:
        os.makedirs(_pipelines_dir(), exist_ok=True)
        try:
            with open(self._path, 'w', encoding='utf-8') as fh:
                json.dump(pipelines, fh, indent=2, sort_keys=True)
        except OSError as exc:
            raise RuntimeError(f"Could not save pipeline: {exc}") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_pipelines(self) -> list:
        """Return saved pipeline names, alphabetically."""
        return sorted(self._load_all().keys())

    def save_pipeline(self, name: str, steps: list) -> None:
        """Save (or silently overwrite) a named pipeline."""
        name = name.strip()
        if not name:
            raise ValueError("Pipeline name cannot be empty.")
        if not steps:
            raise ValueError("Pipeline must contain at least one step.")
        pipelines = self._load_all()
        pipelines[name] = {
            'steps': [dict(step) for step in steps],
            'created': datetime.now().isoformat(),
        }
        self._save_all(pipelines)
        logger.info("Saved batch pipeline %r (%d steps)", name, len(steps))

    def load_pipeline(self, name: str) -> list:
        """Return a copy of the steps list for a saved pipeline."""
        pipelines = self._load_all()
        if name not in pipelines:
            raise KeyError(f"No pipeline named {name!r}")
        return [dict(step) for step in pipelines[name].get('steps', [])]

    def get_pipeline_info(self, name: str) -> dict:
        """Return the full stored record ({'steps': ..., 'created': ...})
        for a saved pipeline — used where the creation timestamp matters,
        not just the replayable steps."""
        pipelines = self._load_all()
        if name not in pipelines:
            raise KeyError(f"No pipeline named {name!r}")
        record = pipelines[name]
        return {
            'steps': [dict(step) for step in record.get('steps', [])],
            'created': record.get('created'),
        }

    def delete_pipeline(self, name: str) -> None:
        """Remove a saved pipeline, if present. No-op if it doesn't exist."""
        pipelines = self._load_all()
        if name in pipelines:
            del pipelines[name]
            self._save_all(pipelines)
            logger.info("Deleted batch pipeline %r", name)
