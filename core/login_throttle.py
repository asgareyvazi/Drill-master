"""Persistent per-account login throttling with exponential lockout (M43).

Policy (all values configurable through the environment; invalid values fall
back to the default with a warning - they never disable throttling):

* ``DRILLMASTER_LOGIN_MAX_FAILURES`` (default 5, 1..100): consecutive failures
  within the window that lock the account;
* ``DRILLMASTER_LOGIN_FAILURE_WINDOW_SECONDS`` (default 900): a failure older
  than this no longer counts;
* ``DRILLMASTER_LOGIN_LOCKOUT_SECONDS`` (default 300): first lockout length;
  each further lockout before a successful login doubles it ...
* ``DRILLMASTER_LOGIN_LOCKOUT_MAX_SECONDS`` (default 3600): ... up to this cap.

State lives in the ``login_throttle`` table keyed by a digest of the
normalized submitted username (whether or not the account exists; the raw
input is never stored), so it survives restarts and is
shared by concurrent processes. The failure counter is advanced by a single
atomic UPSERT; that statement also takes SQLite's write lock, so the lockout
decision made next in the same transaction cannot interleave with another
writer. Callers show one generic message for wrong credentials and for a
locked account.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThrottlePolicy:
    max_failures: int = 5
    window_seconds: int = 900
    lockout_seconds: int = 300
    lockout_max_seconds: int = 3600

    def lockout_for(self, previous_lockouts: int) -> timedelta:
        seconds = self.lockout_seconds * (2 ** min(max(previous_lockouts, 0), 20))
        return timedelta(seconds=min(seconds, self.lockout_max_seconds))


_BOUNDS = {
    "max_failures": ("DRILLMASTER_LOGIN_MAX_FAILURES", 1, 100),
    "window_seconds": ("DRILLMASTER_LOGIN_FAILURE_WINDOW_SECONDS", 1, 7 * 86400),
    "lockout_seconds": ("DRILLMASTER_LOGIN_LOCKOUT_SECONDS", 1, 86400),
    "lockout_max_seconds": ("DRILLMASTER_LOGIN_LOCKOUT_MAX_SECONDS", 1, 7 * 86400),
}


def policy_from_environment(environ=None) -> ThrottlePolicy:
    environ = os.environ if environ is None else environ
    defaults = ThrottlePolicy()
    values = {}
    for name, (variable, low, high) in _BOUNDS.items():
        raw = environ.get(variable)
        value = getattr(defaults, name)
        if raw not in (None, ""):
            try:
                parsed = int(str(raw).strip())
            except ValueError:  # silent-ok: warned just below, default kept
                parsed = None
            if parsed is None or not low <= parsed <= high:
                logger.warning("Ignoring invalid %s (expected an integer %d..%d); using %d",
                               variable, low, high, value)
            else:
                value = parsed
        values[name] = value
    if values["lockout_max_seconds"] < values["lockout_seconds"]:
        logger.warning("DRILLMASTER_LOGIN_LOCKOUT_MAX_SECONDS is below the base lockout; using the base value")
        values["lockout_max_seconds"] = values["lockout_seconds"]
    return ThrottlePolicy(**values)


def normalize_username(username) -> str:
    return str(username or "").strip().casefold()


def throttle_key(username) -> str:
    """Digest of the normalized submitted name.

    Users occasionally type a password into the username field; storing a
    digest keeps such input out of the database while still letting an
    administrator unlock (and list) accounts by name.
    """
    import hashlib

    return hashlib.sha256(("drillmaster-login-throttle:" + normalize_username(username)).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _fmt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S.%f")  # SQLAlchemy's SQLite DateTime storage format


def locked_until(connection, key: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Return the lock expiry if ``key`` is locked at ``now``, else ``None``."""
    now = now or _now()
    row = connection.execute(text("SELECT locked_until FROM login_throttle WHERE username_key = :k"),
                             {"k": key}).fetchone()
    until = _parse(row[0]) if row else None
    return until if until is not None and until > now else None


@dataclass(frozen=True)
class FailureOutcome:
    failed_count: int
    locked_until: Optional[datetime]
    newly_locked: bool


def record_failure(connection, key: str, policy: ThrottlePolicy,
                   now: Optional[datetime] = None) -> FailureOutcome:
    """Count one failed attempt atomically and lock the key when due.

    Must run inside the caller's transaction; the first statement acquires
    SQLite's write lock, serializing concurrent failures for all keys.
    """
    now = now or _now()
    window_start = now - timedelta(seconds=policy.window_seconds)
    connection.execute(text(
        "INSERT INTO login_throttle (username_key, failed_count, lockouts, first_failed_at, last_failed_at) "
        "VALUES (:k, 1, 0, :now, :now) "
        "ON CONFLICT(username_key) DO UPDATE SET "
        " failed_count = CASE WHEN last_failed_at IS NULL OR last_failed_at < :ws THEN 1 ELSE failed_count + 1 END, "
        " first_failed_at = CASE WHEN last_failed_at IS NULL OR last_failed_at < :ws THEN :now ELSE first_failed_at END, "
        " last_failed_at = :now"
    ), {"k": key, "now": _fmt(now), "ws": _fmt(window_start)})
    failed_count, lockouts = connection.execute(
        text("SELECT failed_count, lockouts FROM login_throttle WHERE username_key = :k"), {"k": key}).fetchone()
    if failed_count < policy.max_failures:
        return FailureOutcome(int(failed_count), None, False)
    until = now + policy.lockout_for(int(lockouts))
    connection.execute(text(
        "UPDATE login_throttle SET locked_until = :until, lockouts = lockouts + 1, failed_count = 0 "
        "WHERE username_key = :k"), {"k": key, "until": _fmt(until)})
    return FailureOutcome(int(failed_count), until, True)


def clear(connection, key: str) -> bool:
    """Forget all throttle state for ``key`` (successful login or admin unlock)."""
    result = connection.execute(text("DELETE FROM login_throttle WHERE username_key = :k"), {"k": key})
    return bool(result.rowcount)


def locked_accounts(connection, usernames, now: Optional[datetime] = None) -> list[dict]:
    """Currently locked keys, named when they match one of ``usernames``."""
    now = now or _now()
    names = {throttle_key(name): name for name in usernames}
    rows = connection.execute(text(
        "SELECT username_key, locked_until, lockouts FROM login_throttle "
        "WHERE locked_until IS NOT NULL")).fetchall()
    out = [{"username": names.get(key), "locked_until": _parse(until), "lockouts": int(count)}
           for key, until, count in rows if _parse(until) and _parse(until) > now]
    return sorted(out, key=lambda row: (row["username"] is None, row["username"] or ""))
