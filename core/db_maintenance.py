"""Verified backups of the DrillMaster SQLite database (M43).

Backups
-------
* Snapshot with SQLite's online backup API from a read-only connection (WAL
  content included), into a ``.drillmaster-backup-*.partial`` file in the
  backup directory. The copy is converted to a single self-contained file
  (``journal_mode=DELETE``) and verified (``integrity_check``,
  ``foreign_key_check``, application tables, schema version) BEFORE it gets
  its final name. Unverified copies are deleted and reported as failures.
* Final names are unique (UTC timestamp with microseconds plus a random
  suffix) and claimed with exclusive creation, so an existing file is never
  overwritten. A small manifest (``<name>.json``: format, kind, schema
  version, UTC time, size, SHA-256, application version - no data) is written
  next to the file. A backup counts as verified only if its manifest matches
  the file's size and digest.
* Retention keeps the newest ``DRILLMASTER_BACKUP_KEEP`` verified backups
  (default 10) and runs only after a new backup was verified. It never deletes
  unverified/unknown files, pre-restore safety copies, the live database or the
  newest verified backup.
* One maintenance operation (backup or restore) at a time: an in-process lock
  plus an OS file lock on ``.drillmaster-maintenance.lock`` in the backup
  directory. The OS releases that lock when a process exits, so a crashed
  instance cannot leave a permanent stale lock.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from core import sqlite_connection

logger = logging.getLogger(__name__)

MAINTAIN_DATABASE = "can_maintain_database"
FORMAT_VERSION = 1
KIND_BACKUP = "backup"
KIND_SAFETY = "pre-restore"
_PREFIX = {KIND_BACKUP: "drillmaster_backup", KIND_SAFETY: "drillmaster_prerestore"}
NAME_PATTERN = re.compile(r"^(drillmaster_backup|drillmaster_prerestore)_(\d{8}T\d{12}Z)_([0-9a-f]{8})\.db$")
PARTIAL_PREFIX = ".drillmaster-backup-"
STAGED_PREFIX = ".drillmaster-restore-"
LOCK_NAME = ".drillmaster-maintenance.lock"
JOURNAL_NAME = "maintenance_journal.jsonl"
REQUIRED_TABLES = ("schema_version", "users", "companies", "projects", "wells", "daily_reports", "audit_logs")
MIN_RESTORE_SCHEMA = 1
MAX_RESTORE_BYTES = 8 * 1024 ** 3

KEEP_ENV = "DRILLMASTER_BACKUP_KEEP"
INTERVAL_ENV = "DRILLMASTER_BACKUP_INTERVAL_MINUTES"
DEFAULT_KEEP = 10
DEFAULT_INTERVAL_MINUTES = 30


class MaintenanceError(RuntimeError):
    """A backup/restore step failed; the message never contains database rows."""


class MaintenanceBusy(MaintenanceError):
    """Another backup/restore runs, or transactions did not finish in time."""


class VerificationError(MaintenanceError):
    """A database file failed integrity, foreign-key or schema verification."""


def _int_setting(name: str, default: int, low: int, high: int, *, allow_zero: bool = False) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning("Ignoring invalid %s (not an integer); using %d", name, default)
        return default
    if (allow_zero and value == 0) or low <= value <= high:
        return value
    logger.warning("Ignoring out-of-range %s (expected %d..%d%s); using %d",
                   name, low, high, " or 0" if allow_zero else "", default)
    return default


def retention_count() -> int:
    return _int_setting(KEEP_ENV, DEFAULT_KEEP, 1, 1000)


def interval_minutes() -> int:
    """Automatic backup interval; 0 disables scheduling."""
    return _int_setting(INTERVAL_ENV, DEFAULT_INTERVAL_MINUTES, 5, 1440, allow_zero=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return  # directories cannot be opened for fsync on Windows
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _schema_version(connection) -> Optional[int]:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "schema_version" not in tables:
        return None
    row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else None


def verify_integrity(path) -> None:
    """``integrity_check`` and ``foreign_key_check`` only (any SQLite file)."""
    try:
        connection = sqlite_connection.connect(path, read_only=True, timeout_ms=5000)
    except sqlite3.DatabaseError as exc:
        raise VerificationError(f"not a readable SQLite database ({type(exc).__name__})") from exc
    try:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise VerificationError("integrity_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise VerificationError("foreign_key_check found violations")
    except sqlite3.DatabaseError as exc:
        raise VerificationError(f"database could not be verified ({type(exc).__name__})") from exc
    finally:
        connection.close()


def verify_database_file(path, *, max_version: int, require_version: Optional[int] = None,
                         min_version: int = MIN_RESTORE_SCHEMA) -> dict:
    """Verify a DrillMaster database file through a read-only connection.

    Raises :class:`VerificationError`; returns ``{"schema_version": int}``.
    """
    path = Path(path)
    if not path.is_file():
        raise VerificationError("database file is missing")
    try:
        connection = sqlite_connection.connect(path, read_only=True, timeout_ms=5000)
    except sqlite3.DatabaseError as exc:
        raise VerificationError(f"not a readable SQLite database ({type(exc).__name__})") from exc
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        if integrity != [("ok",)]:
            raise VerificationError(f"integrity_check failed ({len(integrity)} problem(s))")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise VerificationError(f"foreign_key_check found {len(violations)} violation(s)")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [name for name in REQUIRED_TABLES if name not in tables]
        if missing:
            raise VerificationError(f"not a DrillMaster database (missing tables: {', '.join(missing)})")
        version = _schema_version(connection)
    except sqlite3.DatabaseError as exc:
        raise VerificationError(f"database could not be verified ({type(exc).__name__})") from exc
    finally:
        connection.close()
    if version is None:
        raise VerificationError("database has no schema version")
    if version > max_version:
        raise VerificationError(f"schema version {version} is newer than supported ({max_version})")
    if version < min_version:
        raise VerificationError(f"schema version {version} is older than supported ({min_version})")
    if require_version is not None and version != require_version:
        raise VerificationError(f"schema version {version}; expected {require_version}")
    return {"schema_version": version}


def snapshot(source, destination) -> None:
    """Online-backup ``source`` into a NEW file ``destination`` (single file, DELETE journal)."""
    source_connection = sqlite_connection.connect(source, read_only=True)
    try:
        target = sqlite3.connect(str(destination))
        try:
            with target:
                source_connection.backup(target)
            mode = str(target.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
            if mode != "delete":
                raise VerificationError(f"snapshot journal mode is {mode}, expected delete")
        finally:
            target.close()
    finally:
        source_connection.close()


def _claim_new_name(path: Path) -> None:
    """Create ``path`` exclusively (fails if it exists) so promotion never overwrites."""
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)


def _remove(path: Optional[Path], what: str) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove %s: %s", what, path.name)


# ---------------------------------------------------------------- locking

class _ProcessLock:
    """Advisory OS lock on a file; released by the OS if the process dies."""

    def __init__(self, path: Path):
        self.path = path
        self._handle = None

    def acquire(self, timeout: float) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    handle.close()
                    return False
                time.sleep(0.05)

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


# ---------------------------------------------------------------- authorization and audit

def require_permission(manager, actor, operation: str):
    """Service-boundary check for ``can_maintain_database``; denials are audited."""
    from core.authorization import AuthorizationError

    actor = actor if actor is not None else manager._authorization_state().principal
    try:
        allowed = actor is not None and bool(actor.has_permission(MAINTAIN_DATABASE))
    except Exception:
        logger.exception("Permission resolution failed; database %s denied", operation)
        allowed = False
    if not allowed:
        try:
            manager._record_authorization_denials([{
                "table": "database", "operation": operation, "required": [MAINTAIN_DATABASE],
                "user_id": getattr(actor, "user_id", None),
                "username": str(getattr(actor, "username", "") or "")}])
        except Exception:
            logger.exception("Could not record a database %s denial in the audit log", operation)
        raise AuthorizationError("database", operation, (MAINTAIN_DATABASE,))
    return actor


def _actor_fields(actor, scheduled: bool) -> tuple[Optional[int], str]:
    if scheduled:
        return None, "system:backup-scheduler"
    return getattr(actor, "user_id", None), (str(getattr(actor, "username", "") or "")[:50] or "unknown")


def write_audit(db_path, entries) -> None:
    """Write AuditLog rows through a short-lived connection of its own.

    The application's shared connection may be inside another thread's
    transaction; a separate connection keeps the audit write atomic on its own.
    Raises on failure (callers decide the policy).
    """
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import NullPool

    from core.authorization import system_scope
    from core.database import AuditLog

    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool, hide_parameters=True)
    event.listen(engine, "connect", lambda connection, _record: sqlite_connection.configure(connection))
    try:
        with system_scope():
            session = sessionmaker(bind=engine)()
            try:
                for entry in entries:
                    session.add(AuditLog(
                        action=entry["action"][:50], entity_type="database",
                        entity_name=str(entry.get("name") or "")[:200] or None,
                        user_id=entry.get("user_id"), username=entry.get("username"),
                        details=json.dumps(entry.get("details") or {}, sort_keys=True)[:1000],
                        timestamp=entry.get("timestamp") or _utc_now().replace(tzinfo=None)))
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
    finally:
        engine.dispose()


# ---------------------------------------------------------------- backups

@dataclass
class BackupResult:
    ok: bool
    path: Optional[str] = None
    manifest: Optional[dict] = None
    error: Optional[str] = None
    skipped: bool = False
    removed: list = field(default_factory=list)
    retention_errors: list = field(default_factory=list)
    audit_recorded: Optional[bool] = None


class BackupService:
    def __init__(self, manager, backup_dir=None, keep: Optional[int] = None):
        from core.runtime_config import backup_dir as configured_backup_dir

        self.manager = manager
        self.backup_dir = Path(backup_dir) if backup_dir else configured_backup_dir()
        self.keep = keep if keep is not None else retention_count()
        if self.keep < 1:
            raise ValueError("retention must keep at least one verified backup")
        self._thread_lock = threading.Lock()
        self._closed = False
        self.fault: Optional[Callable[[str], None]] = None  # test-only fault injection

    # -- infrastructure
    def _inject(self, stage: str) -> None:
        if self.fault is not None:
            self.fault(stage)

    @contextlib.contextmanager
    def exclusive(self, timeout: float = 0.0):
        """Hold the maintenance locks (this process and other instances)."""
        acquired = (self._thread_lock.acquire(timeout=timeout) if timeout > 0
                    else self._thread_lock.acquire(blocking=False))
        if not acquired:
            raise MaintenanceBusy("another backup or restore is already running")
        process_lock = _ProcessLock(self.backup_dir / LOCK_NAME)
        try:
            if not process_lock.acquire(timeout):
                raise MaintenanceBusy("another application instance is running a backup or restore")
            try:
                yield
            finally:
                process_lock.release()
        finally:
            self._thread_lock.release()

    def shutdown(self) -> None:
        """Refuse new backups (application shutdown)."""
        self._closed = True

    @property
    def live_path(self) -> Path:
        return Path(self.manager.db_path).expanduser()

    # -- creation
    def _new_name(self, kind: str) -> Path:
        stamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
        return self.backup_dir / f"{_PREFIX[kind]}_{stamp}_{secrets.token_hex(4)}.db"

    def _claim_unique_name(self, kind: str, attempts: int = 5) -> Path:
        """Claim a new final name; an existing file is never reused or touched."""
        for _ in range(attempts):
            candidate = self._new_name(kind)
            try:
                _claim_new_name(candidate)
                return candidate
            except FileExistsError:
                logger.warning("Backup name collision on %s; choosing another name", candidate.name)
        raise MaintenanceError("could not choose a unique backup name")

    def _create(self, kind: str) -> BackupResult:
        """Snapshot, verify, promote under a new name, write the manifest."""
        live = self.live_path
        if self.manager.db_path == ":memory:" or not live.is_file():
            return BackupResult(False, error="no file database to back up")
        current = int(self.manager.schema_version)
        partial = final = None  # final is set only once this call has claimed the name
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            partial = self.backup_dir / f"{PARTIAL_PREFIX}{secrets.token_hex(8)}.partial"
            snapshot(live, partial)
            self._inject("verify")
            info = verify_database_file(partial, max_version=current, require_version=current)
            size, digest = partial.stat().st_size, _sha256(partial)
            final = self._claim_unique_name(kind)
            self._inject("promote")
            os.replace(partial, final)
            partial = None
            if final.stat().st_size != size or _sha256(final) != digest:
                raise VerificationError("promoted backup does not match the verified copy")
            manifest = {"format": FORMAT_VERSION, "kind": kind, "file": final.name,
                        "schema_version": info["schema_version"],
                        "created_utc": _utc_now().isoformat(timespec="seconds"),
                        "size": size, "sha256": digest, "app_version": _app_version()}
            self._inject("manifest")
            temporary_manifest = final.with_name(f"{PARTIAL_PREFIX}{secrets.token_hex(8)}.json")
            temporary_manifest.write_text(json.dumps(manifest, sort_keys=True, indent=1), encoding="utf-8")
            os.replace(temporary_manifest, final.with_suffix(".json"))
            _fsync_directory(self.backup_dir)
            logger.info("Verified database %s created: %s", kind, final.name)
            return BackupResult(True, path=str(final), manifest=manifest)
        except (OSError, sqlite3.Error, MaintenanceError) as exc:
            logger.error("Database %s failed (%s): %s", kind, type(exc).__name__, exc)
            _remove(partial, "incomplete backup")
            if final is not None:  # claimed by this call but never completed: never valid
                _remove(final, "unverified backup")
                _remove(final.with_suffix(".json"), "backup manifest")
            return BackupResult(False, error=f"{type(exc).__name__}: {exc}")

    def create_backup(self, actor=None, *, scheduled: bool = False) -> BackupResult:
        """Create a verified backup and apply retention.

        Interactive calls require ``can_maintain_database``; scheduled calls
        run as the explicit ``system:backup-scheduler`` identity. The backup
        outcome is recorded in the audit log; if that write fails the result
        still reports the backup outcome truthfully and ``audit_recorded`` is
        False (the failure is logged, never hidden).
        """
        if not scheduled:
            actor = require_permission(self.manager, actor, "backup")
        if self._closed:
            return BackupResult(False, error="backup service is shut down", skipped=True)
        try:
            with self.exclusive(timeout=0):
                result = self._create(KIND_BACKUP)
                if result.ok:
                    self._apply_retention(result)
        except MaintenanceBusy as exc:
            result = BackupResult(False, error=str(exc), skipped=True)
        user_id, username = _actor_fields(actor, scheduled)
        try:
            self._inject("audit")
            write_audit(self.live_path, [{
                "action": "database_backup" if result.ok else "database_backup_failed",
                "name": Path(result.path).name if result.path else None,
                "user_id": user_id, "username": username,
                "details": {"scheduled": scheduled, "skipped": result.skipped,
                            "schema_version": (result.manifest or {}).get("schema_version"),
                            "size": (result.manifest or {}).get("size"),
                            "removed": len(result.removed), "retention_errors": len(result.retention_errors),
                            "error": (result.error or "")[:200] or None}}])
            result.audit_recorded = True
        except Exception:
            logger.exception("Database backup outcome could not be written to the audit log")
            result.audit_recorded = False
        return result

    # -- inventory and retention
    def read_manifest(self, path: Path, *, deep: bool = True) -> Optional[dict]:
        """The manifest of a managed backup if it matches the file, else None."""
        path = Path(path)
        match = NAME_PATTERN.match(path.name)
        manifest_path = path.with_suffix(".json")
        if not match or path.is_symlink() or not path.is_file() or not manifest_path.is_file():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            size = path.stat().st_size
            if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT_VERSION
                    or manifest.get("file") != path.name or manifest.get("size") != size
                    or manifest.get("kind") not in _PREFIX
                    or _PREFIX[manifest["kind"]] != match.group(1)):
                return None
            if deep and manifest.get("sha256") != _sha256(path):
                return None
            return manifest
        except (OSError, ValueError) as exc:
            logger.warning("Unreadable backup manifest %s (%s)", manifest_path.name, type(exc).__name__)
            return None

    def list_backups(self, *, kinds=(KIND_BACKUP, KIND_SAFETY), deep: bool = False) -> list:
        """Verified managed backups, newest first: ``[(path, manifest), ...]``."""
        if not self.backup_dir.is_dir():
            return []
        found = []
        for path in self.backup_dir.iterdir():
            manifest = self.read_manifest(path, deep=deep) if NAME_PATTERN.match(path.name) else None
            if manifest and manifest["kind"] in kinds:
                found.append((path, manifest))
        found.sort(key=lambda item: (NAME_PATTERN.match(item[0].name).group(2), item[0].name), reverse=True)
        return found

    def _apply_retention(self, result: BackupResult) -> None:
        live = self.live_path.resolve()
        verified = self.list_backups(kinds=(KIND_BACKUP,), deep=True)
        newest = Path(result.path).resolve() if result.path else None
        for path, _manifest in verified[self.keep:]:
            resolved = path.resolve()
            if resolved == live or resolved == newest or resolved.parent != self.backup_dir.resolve():
                continue
            try:
                path.unlink()
                _remove(path.with_suffix(".json"), "backup manifest")
                result.removed.append(path.name)
            except OSError as exc:  # e.g. a Windows lock held by an antivirus or viewer
                logger.warning("Retention could not remove %s (%s)", path.name, type(exc).__name__)
                result.retention_errors.append(path.name)


def _app_version() -> Optional[str]:
    try:
        from core.version import __version__
        return str(__version__)
    except ImportError:
        logger.warning("Application version unavailable for the backup manifest")
        return None


# ---------------------------------------------------------------- scheduling

class BackupScheduler:
    """Runs scheduled backups on one background thread; never overlaps.

    ``stop()`` prevents any new run and waits for a running one.
    """

    def __init__(self, service: BackupService, interval_seconds: float,
                 on_result: Optional[Callable[[BackupResult], None]] = None):
        self.service = service
        self.interval = float(interval_seconds)
        self.on_result = on_result
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.runs = 0

    def start(self) -> bool:
        if self.interval <= 0 or self._stop.is_set() or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._loop, name="drillmaster-backup-scheduler", daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                result = self.service.create_backup(scheduled=True)
                self.runs += 1
                if not result.ok and not result.skipped:
                    logger.error("Scheduled database backup failed: %s", result.error)
                if self.on_result is not None:
                    self.on_result(result)
            except Exception:  # keep the schedule alive; the next interval retries
                logger.exception("Scheduled database backup raised unexpectedly")

    def stop(self, timeout: float = 60.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True
