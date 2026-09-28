"""Offline full-database reset with secure preflight and atomic file promotion.

Close every application instance first. Settings/logs/backups outside the DB
are deliberately preserved. Never remove the live database before a complete
replacement has been initialized and validated.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from core.credential_policy import runtime_environment
from core.database import DatabaseManager


def reset_configured_database() -> Path:
    manager = DatabaseManager()
    mode = runtime_environment()
    if manager.db_path == ":memory:":
        raise ValueError("Offline reset requires a file-backed database.")
    passwords = manager._bootstrap_passwords()  # preflight BEFORE filesystem mutation
    target = Path(manager.db_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=".drillmaster-reset-", suffix=".db", dir=target.parent)
    os.close(fd)
    candidate_path = Path(filename)
    candidate = DatabaseManager(bootstrap_passwords=passwords)
    passwords.clear()
    candidate.db_path = str(candidate_path)
    try:
        if not candidate.initialize():
            raise RuntimeError("Reset preparation failed; the existing database is unchanged. Check initialization diagnostics.")
        with candidate.session_scope() as session:
            candidate._reject_unsafe_existing_credentials(session)
        candidate.close()
        # A closed SQLite database checkpoints its WAL. Refuse promotion if it
        # is not self-contained; never move a main file without committed WAL.
        if Path(f"{candidate_path}-wal").exists() and Path(f"{candidate_path}-wal").stat().st_size:
            raise RuntimeError("Reset candidate is still open; existing database was not replaced.")
        if runtime_environment() != mode:
            raise RuntimeError("Environment changed during reset; existing database was not replaced.")
        if target.exists():
            # Drain WAL and leave a self-contained old file BEFORE replacement.
            # Busy/locked databases refuse here (Windows handles also refuse
            # os.replace); no unlink-first or Unix-only deletion logic.
            connection = sqlite3.connect(str(target), timeout=1)
            try:
                busy, _, _ = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if busy:
                    raise RuntimeError("Close all DrillMaster instances before resetting the database.")
                journal = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
                if journal.lower() != "delete":
                    raise RuntimeError("Cannot obtain offline database access; close all application instances.")
                connection.execute("BEGIN EXCLUSIVE")
                connection.rollback()
            finally:
                connection.close()
        os.replace(candidate_path, target)  # same filesystem; old DB retained if this fails
        return target
    finally:
        candidate.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(f"{candidate_path}{suffix}").unlink()
            except FileNotFoundError:
                pass
