"""One place that configures every DrillMaster SQLite connection (M43).

SQLite settings such as ``foreign_keys`` and ``busy_timeout`` are
per-connection: a PRAGMA run on one connection does not configure the next.
Every connection the application opens therefore goes through
:func:`configure` - the SQLAlchemy engine's ``connect`` hook
(``DatabaseManager.initialize``) and :func:`connect` for direct ``sqlite3``
use (backup, restore, maintenance).

Settings
--------
* ``foreign_keys=ON``  - verified by read-back; a connection that does not
  enforce foreign keys is refused (fail closed).
* ``busy_timeout``     - how long a connection waits for another writer's lock
  before raising ``database is locked``. ``DRILLMASTER_DB_BUSY_TIMEOUT_MS``
  (default 30000 = the previous ``timeout=30``; 100..600000; an invalid value
  falls back to the default with a warning).
* ``journal_mode=WAL`` - a database-level, persistent setting. It is read
  first and only changed when different, so normal connections do not issue a
  mode change. Switching needs exclusive access; when it cannot be obtained
  (another process holds the database, or the file system does not support
  WAL) the connection keeps the current mode and a warning is logged - it is
  never reported as WAL. Read-only connections never change the mode.
* ``synchronous=NORMAL`` - with WAL, committed transactions survive an
  application crash; the most recent ones can be lost on power failure or OS
  crash, but the database stays consistent.

WAL lets readers proceed while one writer commits; it does not allow two
concurrent writers. A second writer waits up to ``busy_timeout`` and then
fails with ``database is locked``.

Connection pool (M47)
---------------------
A file-backed ``DatabaseManager`` uses a bounded ``QueuePool``: every session
checks out its *own* DB-API connection, so a rollback, close or failed flush in
one session can never touch another session's transaction. Two different
waits exist and are reported differently:

* ``pool_timeout`` (``DRILLMASTER_DB_POOL_TIMEOUT_S``, default 30, 1..600)
  - how long a checkout waits for a free pooled connection when
  ``pool_size + max_overflow`` connections are all in use; it then raises
  SQLAlchemy's ``TimeoutError`` ("QueuePool limit ... reached").
* ``busy_timeout`` - how long a statement waits for another connection's
  SQLite write lock; it then raises ``database is locked``.

``DRILLMASTER_DB_POOL_SIZE`` (default 5, 1..32) sets the number of kept
connections; up to the same number of overflow connections are opened under
load and closed when returned. Invalid values fall back to the default with a
warning. An in-memory database (tests only) keeps one shared connection
(``StaticPool``) because each new ``:memory:`` connection is an empty database.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_ENV = "DRILLMASTER_DB_BUSY_TIMEOUT_MS"
DEFAULT_BUSY_TIMEOUT_MS = 30_000
_BUSY_TIMEOUT_RANGE = (100, 600_000)
CACHE_SIZE_PAGES = 10_000

POOL_SIZE_ENV = "DRILLMASTER_DB_POOL_SIZE"
DEFAULT_POOL_SIZE = 5
_POOL_SIZE_RANGE = (1, 32)
POOL_TIMEOUT_ENV = "DRILLMASTER_DB_POOL_TIMEOUT_S"
DEFAULT_POOL_TIMEOUT_S = 30
_POOL_TIMEOUT_RANGE = (1, 600)


class ConnectionConfigurationError(sqlite3.DatabaseError):
    """A connection could not be given the required integrity settings."""


def _bounded_int(environ, name: str, default: int, bounds: tuple) -> int:
    environ = os.environ if environ is None else environ
    raw = environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    low, high = bounds
    message = "Ignoring invalid %s (expected an integer %d..%d); using %d"
    try:
        value = int(str(raw).strip())
    except ValueError:
        logger.warning(message, name, low, high, default)
        return default
    if not low <= value <= high:
        logger.warning(message, name, low, high, default)
        return default
    return value


def busy_timeout_ms(environ: Optional[Mapping[str, str]] = None) -> int:
    return _bounded_int(environ, BUSY_TIMEOUT_ENV, DEFAULT_BUSY_TIMEOUT_MS, _BUSY_TIMEOUT_RANGE)


def pool_settings(environ: Optional[Mapping[str, str]] = None) -> dict:
    """``QueuePool`` sizing for a file-backed engine (see the module docstring)."""
    size = _bounded_int(environ, POOL_SIZE_ENV, DEFAULT_POOL_SIZE, _POOL_SIZE_RANGE)
    timeout = _bounded_int(environ, POOL_TIMEOUT_ENV, DEFAULT_POOL_TIMEOUT_S, _POOL_TIMEOUT_RANGE)
    return {"pool_size": size, "max_overflow": size, "pool_timeout": timeout}


def _is_memory(connection) -> bool:
    row = connection.execute("PRAGMA database_list").fetchone()
    return row is None or not row[2]


def configure(connection, *, timeout_ms: Optional[int] = None, read_only: bool = False) -> dict:
    """Apply and verify the DrillMaster settings on a DB-API connection.

    Returns the effective settings read back from the connection.
    """
    timeout_ms = busy_timeout_ms() if timeout_ms is None else int(timeout_ms)
    cursor = connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout={timeout_ms:d}")
        cursor.execute("PRAGMA foreign_keys=ON")
        if not read_only:
            mode = str(cursor.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if mode != "wal" and not _is_memory(connection):
                mode = str(cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
                if mode != "wal":
                    logger.warning("SQLite WAL mode could not be enabled (journal_mode=%s); "
                                   "continuing in the current mode", mode)
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA cache_size={CACHE_SIZE_PAGES:d}")
        if cursor.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise ConnectionConfigurationError("SQLite foreign-key enforcement could not be enabled")
    finally:
        cursor.close()
    return effective_settings(connection)


def effective_settings(connection) -> dict:
    """Read back the settings that matter for integrity and concurrency."""
    return {
        name: connection.execute(f"PRAGMA {name}").fetchone()[0]
        for name in ("foreign_keys", "busy_timeout", "journal_mode", "synchronous")
    }


def connect(path, *, read_only: bool = False, timeout_ms: Optional[int] = None,
            check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a configured ``sqlite3`` connection to an existing or new file.

    ``read_only`` opens with ``mode=ro`` (the file must exist; it is never
    created or switched to another journal mode). ``check_same_thread=False``
    is only for connections owned by a SQLAlchemy pool, which hands a
    connection to one thread at a time (sequential, never concurrent use).
    """
    timeout_ms = busy_timeout_ms() if timeout_ms is None else int(timeout_ms)
    if read_only:
        uri = Path(path).expanduser().resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=timeout_ms / 1000,
                                     check_same_thread=check_same_thread)
    else:
        connection = sqlite3.connect(str(Path(path).expanduser()), timeout=timeout_ms / 1000,
                                     check_same_thread=check_same_thread)
    try:
        configure(connection, timeout_ms=timeout_ms, read_only=read_only)
    except BaseException:
        connection.close()
        raise
    return connection
