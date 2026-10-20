"""Verified backups and safe restore of the DrillMaster SQLite database (M43).

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

Restore
-------
Requires ``can_maintain_database`` (enforced here, not only in the UI) and an
explicit confirmation. Sequence (each step must succeed before the next):

1. Validate the candidate: a managed backup file directly inside the backup
   directory (no symlink, no traversal), a matching manifest, and full
   verification through a read-only connection.
2. Stage a copy beside the live database (same file system). An older
   supported schema is migrated on the STAGED copy only, then re-verified.
3. Journal ``restore_started`` (sidecar file; failure aborts).
4. Maintenance: new database checkouts are refused, in-flight transactions
   are drained (bounded wait, otherwise abort) and the shared connection is
   disposed.
5. Pre-restore safety copy of the live database, verified; failure aborts.
6. Exclusivity: WAL checkpoint and switch to ``journal_mode=DELETE``, which
   SQLite only allows when no other connection (e.g. another application
   instance) has the database open; otherwise abort.
7. ``os.replace(staged, live)`` - a single rename on the same file system.
8. Reopen through the application's own engine and verify. On failure the
   safety copy is staged and put back the same way, then verified.

The safety copy is never deleted automatically. The live file is never
deleted; it is only replaced by a verified file.
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


class MaintenanceActive(MaintenanceError):
    """Database access was attempted while a restore holds the database."""


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


# ---------------------------------------------------------------- maintenance gate

class MaintenanceGate:
    """Counts checked-out engine connections and can refuse new checkouts."""

    def __init__(self):
        self._condition = threading.Condition()
        self.active = 0
        self.closed = False

    def on_checkout(self, *_args) -> None:
        with self._condition:
            if self.closed:
                raise MaintenanceActive("database maintenance (restore) in progress; try again shortly")
            self.active += 1

    def on_checkin(self, *_args) -> None:
        with self._condition:
            self.active = max(0, self.active - 1)
            self._condition.notify_all()

    def close(self, drain_timeout: float) -> None:
        with self._condition:
            self.closed = True
            if not self._condition.wait_for(lambda: self.active == 0, timeout=drain_timeout):
                self.closed = False
                self._condition.notify_all()
                raise MaintenanceBusy("database transactions did not finish in time; nothing was changed")

    def open(self) -> None:
        with self._condition:
            self.closed = False
            self._condition.notify_all()


def install_gate(manager) -> MaintenanceGate:
    """Attach the maintenance gate to ``manager.engine`` (called by initialize)."""
    from sqlalchemy import event

    gate = getattr(manager, "_maintenance_gate", None)
    if gate is None:
        gate = MaintenanceGate()
        manager._maintenance_gate = gate
    gate.open()
    gate.active = 0
    event.listen(manager.engine, "checkout", gate.on_checkout)
    event.listen(manager.engine, "checkin", gate.on_checkin)
    return gate


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


# ---------------------------------------------------------------- restore

@dataclass
class RestoreResult:
    ok: bool
    stage: str
    error: Optional[str] = None
    safety_copy: Optional[str] = None
    restored_from: Optional[str] = None
    original_intact: bool = True
    recovered: Optional[bool] = None
    journal_complete: bool = False
    audit_recorded: Optional[bool] = None
    operation_id: Optional[str] = None


class RestoreJournal:
    """Append-only JSON-lines record of restore attempts beside the backups.

    It survives replacing the database (whose own audit table comes from the
    restored snapshot). Plain file: anyone with write access to the backup
    directory can alter it - it is evidence, not tamper-proof.
    """

    def __init__(self, directory: Path):
        self.path = Path(directory) / JOURNAL_NAME

    def append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"time_utc": _utc_now().isoformat(timespec="seconds"), **event}, sort_keys=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def read(self) -> list:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


class RestoreService:
    def __init__(self, manager, backups: BackupService, *, drain_timeout: float = 15.0,
                 lock_timeout: float = 30.0):
        self.manager = manager
        self.backups = backups
        self.journal = RestoreJournal(backups.backup_dir)
        self.drain_timeout = drain_timeout
        self.lock_timeout = lock_timeout
        self.fault: Optional[Callable[[str], None]] = None  # test-only fault injection

    def _inject(self, stage: str) -> None:
        if self.fault is not None:
            self.fault(stage)

    # -- validation
    def validate_candidate(self, candidate) -> tuple[Path, dict, dict]:
        """Path policy, manifest and full read-only verification of a candidate."""
        backup_dir = self.backups.backup_dir.resolve()
        path = Path(candidate)
        if path.is_symlink():
            raise VerificationError("symbolic links are not accepted as restore candidates")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise VerificationError("restore candidate does not exist") from exc
        if not resolved.is_file():
            raise VerificationError("restore candidate is not a regular file")
        if resolved.parent != backup_dir or not NAME_PATTERN.match(resolved.name):
            raise VerificationError("only managed backups inside the backup directory can be restored")
        if resolved == self.backups.live_path.resolve():
            raise VerificationError("the live database cannot be its own restore candidate")
        size = resolved.stat().st_size
        if size <= 0 or size > MAX_RESTORE_BYTES:
            raise VerificationError("restore candidate size is outside the accepted range")
        manifest = self.backups.read_manifest(resolved, deep=True)
        if manifest is None:
            raise VerificationError("backup manifest is missing or does not match the file")
        info = verify_database_file(resolved, max_version=int(self.manager.schema_version))
        if info["schema_version"] != manifest.get("schema_version"):
            raise VerificationError("backup schema version does not match its manifest")
        return resolved, manifest, info

    def _stage(self, source: Path, operation_id: str, migrate: bool) -> Path:
        live = self.backups.live_path
        staged = live.with_name(f"{STAGED_PREFIX}{operation_id}.staged")
        snapshot(source, staged)
        if migrate:
            self._migrate_staged(staged)
        verify_database_file(staged, max_version=int(self.manager.schema_version),
                             require_version=int(self.manager.schema_version))
        return staged

    def _migrate_staged(self, staged: Path) -> None:
        """Apply the application's own migrations to the STAGED copy only."""
        from core.database import DatabaseManager

        migrator = DatabaseManager()
        migrator.db_path = str(staged)
        try:
            if not migrator.initialize():
                raise VerificationError("staged backup could not be migrated to the current schema")
        finally:
            migrator.close()
        connection = sqlite3.connect(str(staged))
        try:
            mode = str(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
        finally:
            connection.close()
        if mode != "delete":
            raise VerificationError("migrated staged copy could not be made self-contained")

    # -- live database lifecycle
    def _enter_maintenance(self) -> None:
        gate = getattr(self.manager, "_maintenance_gate", None)
        if gate is None or self.manager.engine is None:
            raise MaintenanceError("database is not initialized")
        gate.close(self.drain_timeout)
        self.manager.engine.dispose()

    def _leave_maintenance(self) -> None:
        gate = getattr(self.manager, "_maintenance_gate", None)
        if gate is not None:
            gate.open()

    def _require_exclusive_file(self) -> None:
        """WAL checkpoint, then leave WAL: only possible with no other connection."""
        live = self.backups.live_path
        connection = sqlite_connection.connect(live, timeout_ms=2000)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            mode = str(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
        except sqlite3.OperationalError as exc:
            raise MaintenanceBusy("the database is open in another process; close it and retry") from exc
        finally:
            connection.close()
        if mode != "delete":
            raise MaintenanceBusy("the database is open in another process; close it and retry")
        wal = live.with_name(live.name + "-wal")
        if wal.exists() and wal.stat().st_size > 0:
            raise MaintenanceBusy("the database write-ahead log is still in use")

    def _verify_live(self) -> None:
        """Reopen through the application's engine and prove it is usable."""
        from sqlalchemy import text

        expected = int(self.manager.schema_version)
        with self.manager.engine.connect() as connection:
            if connection.execute(text("PRAGMA integrity_check")).fetchall() != [("ok",)]:
                raise VerificationError("restored database failed integrity_check")
            if connection.execute(text("PRAGMA foreign_key_check")).fetchall():
                raise VerificationError("restored database failed foreign_key_check")
            version = connection.execute(text("SELECT MAX(version) FROM schema_version")).scalar()
            if version != expected:
                raise VerificationError(f"restored schema version {version}; expected {expected}")
            connection.execute(text("SELECT COUNT(*) FROM users")).scalar()
            if connection.execute(text("PRAGMA foreign_keys")).scalar() != 1:
                raise VerificationError("restored connection does not enforce foreign keys")

    def _put_back(self, safety: Path, operation_id: str) -> None:
        """Recovery: replace the live file with the verified safety copy."""
        staged = self.backups.live_path.with_name(f"{STAGED_PREFIX}{operation_id}.recovery")
        try:
            self._enter_maintenance()
            snapshot(safety, staged)
            verify_database_file(staged, max_version=int(self.manager.schema_version),
                                 require_version=int(self.manager.schema_version))
            self._require_exclusive_file()
            os.replace(staged, self.backups.live_path)
            staged = None
        finally:
            _remove(staged, "staged recovery copy")
            self._leave_maintenance()
        self._verify_live()

    def _journal(self, result: RestoreResult, event: str, **extra) -> bool:
        try:
            self._inject(f"journal:{event}")
            self.journal.append({"id": result.operation_id, "event": event, **extra})
            return True
        except Exception:
            logger.exception("Restore journal entry %s could not be written", event)
            return False

    # -- the operation
    def restore(self, candidate, actor=None, *, confirmed: bool = False) -> RestoreResult:
        actor = require_permission(self.manager, actor, "restore")
        result = RestoreResult(False, "confirm", operation_id=secrets.token_hex(6))
        if not confirmed:
            result.error = "restore requires explicit confirmation"
            return result
        user_id, username = _actor_fields(actor, False)
        actor_fields = {"user_id": user_id, "username": username}
        result.stage = "lock"
        try:
            with self.backups.exclusive(timeout=self.lock_timeout):
                self._run(candidate, result, actor_fields)
        except MaintenanceBusy as exc:
            result.error = str(exc)
        self._audit_in_database(result, actor_fields)
        return result

    def _run(self, candidate, result: RestoreResult, actor_fields: dict) -> None:
        staged = None
        in_maintenance = False
        replaced = False
        safety = None
        try:
            result.stage = "validate"
            self._inject("validate")
            source, manifest, info = self.validate_candidate(candidate)
            result.restored_from = source.name

            result.stage = "stage"
            self._inject("stage")
            staged = self._stage(source, result.operation_id,
                                 migrate=info["schema_version"] < int(self.manager.schema_version))

            result.stage = "journal"
            if not self._journal(result, "restore_started", candidate=source.name,
                                 candidate_sha256=manifest["sha256"],
                                 candidate_schema=info["schema_version"], **actor_fields):
                raise MaintenanceError("restore journal could not be written; nothing was changed")

            result.stage = "maintenance"
            self._inject("maintenance")
            self._enter_maintenance()
            in_maintenance = True

            result.stage = "safety_copy"
            self._inject("safety_copy")
            copy = self.backups._create(KIND_SAFETY)
            if not copy.ok:
                raise MaintenanceError(f"pre-restore safety copy failed: {copy.error}")
            safety = Path(copy.path)
            result.safety_copy = safety.name

            result.stage = "exclusive"
            self._inject("exclusive")
            self._require_exclusive_file()

            result.stage = "replace"
            self._inject("replace")
            os.replace(staged, self.backups.live_path)
            staged = None
            replaced = True
            result.original_intact = False  # the safety copy now holds the original

            result.stage = "reopen"
            self._leave_maintenance()
            in_maintenance = False
            self._inject("reopen")
            self._verify_live()

            result.stage = "complete"
            result.ok = True
            result.journal_complete = self._journal(result, "restore_succeeded",
                                                    safety_copy=result.safety_copy, **actor_fields)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            logger.error("Database restore failed at %s: %s", result.stage, result.error)
            if in_maintenance:
                self._leave_maintenance()
                in_maintenance = False
            if replaced and safety is not None:
                try:
                    self._put_back(safety, result.operation_id)
                    result.recovered = True
                    result.original_intact = True
                except Exception as recovery_error:
                    result.recovered = False
                    logger.critical("Restore recovery failed (%s); the verified safety copy %s is kept",
                                    type(recovery_error).__name__, safety.name)
            event = ("restore_failed" if not replaced else
                     "restore_recovered" if result.recovered else "restore_recovery_failed")
            result.journal_complete = self._journal(result, event, stage=result.stage,
                                                    error_class=type(exc).__name__,
                                                    safety_copy=result.safety_copy, **actor_fields)
        finally:
            _remove(staged, "staged restore copy")
            if in_maintenance:
                self._leave_maintenance()

    def _audit_in_database(self, result: RestoreResult, actor_fields: dict) -> None:
        """Record the outcome in the (possibly restored) database's audit log.

        Best effort by policy: the sidecar journal is the durable record; a
        failure here is logged and reported via ``audit_recorded=False``.
        """
        try:
            self._inject("audit")
            write_audit(self.backups.live_path, [{
                "action": "database_restored" if result.ok else "database_restore_failed",
                "name": result.restored_from, **actor_fields,
                "details": {"operation_id": result.operation_id, "stage": result.stage,
                            "safety_copy": result.safety_copy, "recovered": result.recovered,
                            "journal_complete": result.journal_complete,
                            "error": (result.error or "")[:200] or None}}])
            result.audit_recorded = True
        except Exception:
            logger.exception("Restore outcome could not be written to the database audit log")
            result.audit_recorded = False
