"""Temporary-file cleanup and filename sanitising."""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from app.config import Config

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^\w.\- \[\]()+&,]+", re.UNICODE)
_PROTECTED = {"database", "db"}  # TDLib database folder - never touched


def sanitize_filename(name: str, fallback: str = "file.mp4") -> str:
    """Safe basename: no directories, control chars or odd symbols."""
    name = os.path.basename((name or "").replace("\\", "/")).replace("\x00", "").strip()
    name = _UNSAFE.sub("_", name).strip(". ")
    return name[:180] if name else fallback


class CleanupService:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._roots = [config.temp_dir.resolve(), config.files_dir.resolve()]

    def _is_managed(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        if any(part in _PROTECTED for part in resolved.parts):
            return False
        return any(root in resolved.parents for root in self._roots)

    def delete_path(self, path: Path | str | None) -> bool:
        if not path:
            return False
        path = Path(path)
        if not self._is_managed(path):
            logger.warning("Refusing to delete unmanaged path: %s", path.name)
            return False
        try:
            if path.is_file():
                path.unlink()
                logger.info("Temporary file deleted: %s", path.name)
                return True
        except OSError as exc:
            logger.warning("Could not delete %s: %s", path.name, exc)
        return False

    def sweep_stale(self) -> int:
        """Remove leftovers from a previous crash. TDLib's database is kept."""
        removed = 0
        for root in self._roots:
            if not root.exists():
                continue
            for entry in root.iterdir():
                if entry.name in _PROTECTED or entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir() and root == self._config.files_dir.resolve():
                        # TDLib cache folders (videos/, documents/, temp/ ...)
                        for child in entry.rglob("*"):
                            if child.is_file():
                                child.unlink()
                                removed += 1
                        shutil.rmtree(entry, ignore_errors=True)
                    elif entry.is_file() and root == self._config.temp_dir.resolve():
                        entry.unlink()
                        removed += 1
                except OSError:
                    pass
        if removed:
            logger.info("Removed %d stale temporary file(s) on startup", removed)
        return removed

    def free_bytes(self) -> int:
        try:
            return shutil.disk_usage(self._config.files_dir).free
        except OSError:
            return 0
