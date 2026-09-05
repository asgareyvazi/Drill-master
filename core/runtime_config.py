"""Runtime paths and environment configuration for DrillMaster.

The application is a desktop program, so mutable state must not be written
next to the installed source files.  This module is deliberately small and
is the single path-resolution layer used by startup, the database, logging,
backups, and optional local-AI settings.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path


APP_NAME = "DrillMaster"


def _absolute(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve()


def data_dir() -> Path:
    """Return the writable per-user application data directory.

    ``DRILLMASTER_DATA_DIR`` is intended for service accounts, portable
    deployments, and test isolation.  It takes precedence over OS defaults.
    """
    configured = os.getenv("DRILLMASTER_DATA_DIR")
    if configured:
        return _absolute(configured)

    system = platform.system()
    if system == "Windows":
        root = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return _absolute(Path(root) / APP_NAME)
    if system == "Darwin":
        return _absolute(Path.home() / "Library" / "Application Support" / APP_NAME)

    root = os.getenv("XDG_DATA_HOME")
    if root:
        return _absolute(Path(root) / APP_NAME.lower())
    return _absolute(Path.home() / ".local" / "share" / APP_NAME.lower())


def _configured_path(variable: str, default: Path) -> Path:
    value = os.getenv(variable)
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else data_dir() / path


def database_path() -> str:
    """Return the SQLite path, preserving ``:memory:`` for test use."""
    configured = os.getenv("DRILLMASTER_DB_PATH")
    if configured and configured.strip() == ":memory:":
        return ":memory:"
    path = _configured_path("DRILLMASTER_DB_PATH", data_dir() / "drillmaster.db")
    return str(path)


def log_dir() -> Path:
    return _configured_path("DRILLMASTER_LOG_DIR", data_dir() / "logs")


def backup_dir() -> Path:
    return _configured_path("DRILLMASTER_BACKUP_DIR", data_dir() / "backups")


def ai_settings_path() -> Path:
    return _configured_path(
        "DRILLMASTER_AI_SETTINGS_PATH", data_dir() / "config" / "ai_settings.json"
    )


def mapping_memory_path() -> Path:
    return _configured_path(
        "DRILLMASTER_MAPPING_MEMORY_PATH", data_dir() / "config" / "mapping_memory.json"
    )


def standards_path() -> Path:
    return _configured_path(
        "DRILLMASTER_STANDARDS_PATH", data_dir() / "config" / "operational_standards.json"
    )


def ensure_writable_directories() -> None:
    """Create only mutable directories; read-only application assets stay put."""
    for path in (
        Path(database_path()).parent,
        log_dir(),
        backup_dir(),
        ai_settings_path().parent,
        mapping_memory_path().parent,
        standards_path().parent,
    ):
        if str(path) != ".":
            path.mkdir(parents=True, exist_ok=True)


def describe_paths() -> dict[str, str]:
    """Return non-secret paths for diagnostics and the release smoke test."""
    return {
        "data_dir": str(data_dir()),
        "database": database_path(),
        "log_dir": str(log_dir()),
        "backup_dir": str(backup_dir()),
        "ai_settings": str(ai_settings_path()),
        "mapping_memory": str(mapping_memory_path()),
        "standards": str(standards_path()),
    }
