"""Persistent per-account login throttling, lockout, unlock and audit (M43).

Time is controlled by passing explicit ``now`` values or by expiring a lock in
the database; no test sleeps or asserts absolute timings.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine

from core import login_throttle as throttle
from core.authorization import AuthorizationError
from core.database import DatabaseManager
from tests.test_database_migration_acceptance import _configure
from tests.test_data_layer_authorization import Principal

ADMIN_PASSWORD = "admin123"  # test-environment fixture credential (refused in production)


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "auth.sqlite"
    _configure(tmp_path, monkeypatch, path)
    for name in ("MAX_FAILURES", "FAILURE_WINDOW_SECONDS", "LOCKOUT_SECONDS", "LOCKOUT_MAX_SECONDS"):
        monkeypatch.delenv(f"DRILLMASTER_LOGIN_{name}", raising=False)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    yield manager, path
    manager.close()


def _rows(path, sql, *args):
    with sqlite3.connect(path) as connection:
        return connection.execute(sql, args).fetchall()


def _fail(manager, times, username="admin"):
    for _ in range(times):
        assert manager.authenticate_user(username, "wrong-password") is None


# ---------------------------------------------------------------- policy

def test_policy_defaults_overrides_and_invalid_values_never_disable_throttling():
    assert throttle.policy_from_environment({}) == throttle.ThrottlePolicy(5, 900, 300, 3600)
    custom = throttle.policy_from_environment({
        "DRILLMASTER_LOGIN_MAX_FAILURES": "3", "DRILLMASTER_LOGIN_LOCKOUT_SECONDS": "60",
        "DRILLMASTER_LOGIN_LOCKOUT_MAX_SECONDS": "600", "DRILLMASTER_LOGIN_FAILURE_WINDOW_SECONDS": "120"})
    assert custom == throttle.ThrottlePolicy(3, 120, 60, 600)
    for bad in ("0", "-1", "abc", "101", "1.5"):
        assert throttle.policy_from_environment({"DRILLMASTER_LOGIN_MAX_FAILURES": bad}).max_failures == 5
    capped = throttle.policy_from_environment({"DRILLMASTER_LOGIN_LOCKOUT_SECONDS": "900",
                                               "DRILLMASTER_LOGIN_LOCKOUT_MAX_SECONDS": "60"})
    assert capped.lockout_max_seconds == 900


def test_lockout_grows_exponentially_up_to_the_cap():
    policy = throttle.ThrottlePolicy(lockout_seconds=300, lockout_max_seconds=3600)
    assert [policy.lockout_for(n).total_seconds() for n in range(6)] == [300, 600, 1200, 2400, 3600, 3600]


# ---------------------------------------------------------------- lockout behaviour

def test_account_locks_after_the_configured_failures_with_one_generic_outcome(db, monkeypatch):
    manager, path = db
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "3")
    _fail(manager, 2)
    assert manager.authenticate_user("admin", ADMIN_PASSWORD)  # success resets the counter
    _fail(manager, 3)
    # Locked: even the correct password returns the same None as a wrong one.
    assert manager.authenticate_user("admin", ADMIN_PASSWORD) is None
    actions = [a for (a,) in _rows(path, "SELECT action FROM audit_logs WHERE action LIKE 'login_%' ORDER BY id")]
    assert actions.count("login_failed") == 5
    assert actions.count("login_locked") == 1
    assert actions[-1] == "login_rejected_locked"


def test_a_locked_account_is_refused_without_verifying_the_password(db, monkeypatch):
    manager, _ = db
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "1")
    _fail(manager, 1)
    calls = []
    monkeypatch.setattr(DatabaseManager, "_verify_password", lambda self, p, h: calls.append(1) or True)
    assert manager.authenticate_user("admin", ADMIN_PASSWORD) is None
    assert calls == []


def test_lock_persists_across_restarts_and_expires(db, monkeypatch):
    manager, path = db
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "2")
    _fail(manager, 2)
    manager.close()
    reopened = DatabaseManager()
    assert reopened.initialize()
    assert reopened.authenticate_user("admin", ADMIN_PASSWORD) is None
    with sqlite3.connect(path) as connection:  # simulate the lock period elapsing
        connection.execute("UPDATE login_throttle SET locked_until='2000-01-01 00:00:00.000000'")
    assert reopened.authenticate_user("admin", ADMIN_PASSWORD)
    assert _rows(path, "SELECT COUNT(*) FROM login_throttle") == [(0,)]
    reopened.close()


def test_failures_outside_the_window_do_not_accumulate(db):
    manager, _ = db
    policy = throttle.ThrottlePolicy(max_failures=3, window_seconds=60)
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    with manager.engine.begin() as connection:
        key = throttle.throttle_key("someone")
        throttle.record_failure(connection, key, policy, now=t0)
        throttle.record_failure(connection, key, policy, now=t0 + timedelta(seconds=30))
        late = throttle.record_failure(connection, key, policy, now=t0 + timedelta(seconds=200))
    assert late.failed_count == 1 and not late.newly_locked


def test_each_further_lockout_doubles(db):
    manager, _ = db
    policy = throttle.ThrottlePolicy(max_failures=1, lockout_seconds=60, lockout_max_seconds=1000)
    key = throttle.throttle_key("someone")
    t = datetime(2026, 1, 1, 12, 0, 0)
    durations = []
    with manager.engine.begin() as connection:
        for _ in range(3):
            outcome = throttle.record_failure(connection, key, policy, now=t)
            durations.append((outcome.locked_until - t).total_seconds())
            t = outcome.locked_until + timedelta(seconds=1)
    assert durations == [60, 120, 240]


def test_unknown_names_are_throttled_identically_and_never_stored_in_clear(db, monkeypatch):
    manager, path = db
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "2")
    typed = "Correct-Horse-Battery-Staple-typed-as-username"
    _fail(manager, 3, username=typed)
    keys = _rows(path, "SELECT username_key, locked_until FROM login_throttle")
    assert len(keys) == 1 and keys[0][0] == throttle.throttle_key(typed) and keys[0][1] is not None
    dump = "\n".join(sqlite3.connect(path).iterdump())
    assert typed not in dump and typed.casefold() not in dump
    # attempt 1 fails, attempt 2 fails and locks, attempt 3 is rejected while locked
    actions = [a for (a,) in _rows(path, "SELECT action FROM audit_logs WHERE action LIKE 'login_%' ORDER BY id")]
    assert actions == ["login_failed", "login_failed", "login_locked", "login_rejected_locked"]
    assert _rows(path, "SELECT COUNT(*) FROM audit_logs WHERE action LIKE 'login_%' AND username IS NOT NULL") == [(0,)]


def test_username_case_and_spacing_share_one_throttle_key():
    assert throttle.throttle_key(" Admin ") == throttle.throttle_key("admin")
    assert throttle.throttle_key("admin") != throttle.throttle_key("admin2")


def test_concurrent_failures_are_all_counted(db):
    """Parallel failures on independent connections lose no increment."""
    manager, path = db
    policy = throttle.ThrottlePolicy(max_failures=1000)
    key = throttle.throttle_key("admin")
    errors, workers = [], 12

    def worker():
        engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})
        try:
            for _ in range(5):
                with engine.begin() as connection:
                    throttle.record_failure(connection, key, policy)
        except Exception as exc:  # surfaced below
            errors.append(exc)
        finally:
            engine.dispose()

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert _rows(path, "SELECT failed_count FROM login_throttle WHERE username_key=?", key) == [(workers * 5,)]


def test_concurrent_failures_lock_exactly_once_per_threshold(db):
    manager, path = db
    policy = throttle.ThrottlePolicy(max_failures=10, lockout_seconds=60, lockout_max_seconds=60)
    key = throttle.throttle_key("admin")
    outcomes = []

    def worker():
        engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})
        try:
            with engine.begin() as connection:
                outcomes.append(throttle.record_failure(connection, key, policy))
        finally:
            engine.dispose()

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(o.newly_locked for o in outcomes) == 1
    assert _rows(path, "SELECT lockouts, failed_count FROM login_throttle WHERE username_key=?", key) == [(1, 0)]


# ---------------------------------------------------------------- administration

def test_admin_unlock_is_permission_checked_audited_and_fail_closed(db, monkeypatch):
    manager, path = db
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "1")
    _fail(manager, 1)
    users = dict(_rows(path, "SELECT username, id FROM users"))
    with pytest.raises(AuthorizationError):
        manager.unlock_account("admin")  # no actor and no enforced principal
    with pytest.raises(AuthorizationError):
        manager.unlock_account("admin", actor=Principal("engineer", users["engineer"], "engineer"))
    assert manager.authenticate_user("admin", ADMIN_PASSWORD) is None
    admin = Principal("admin", users["admin"], "admin")
    locked = manager.get_locked_accounts(actor=admin)
    assert [row["username"] for row in locked] == ["admin"]
    with pytest.raises(AuthorizationError):
        manager.get_locked_accounts(actor=Principal("viewer", users["viewer"], "viewer"))
    assert manager.unlock_account("admin", actor=admin) is True
    assert manager.authenticate_user("admin", ADMIN_PASSWORD)
    unlocked = _rows(path, "SELECT user_id, entity_name FROM audit_logs WHERE action='account_unlocked'")
    assert unlocked == [(users["admin"], "admin")]
    assert _rows(path, "SELECT COUNT(*) FROM audit_logs WHERE action='authorization_denied'")[0][0] >= 3


def test_unlock_uses_the_enforced_principal_when_no_actor_is_given(db, monkeypatch):
    manager, path = db
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "1")
    _fail(manager, 1, username="engineer")
    users = dict(_rows(path, "SELECT username, id FROM users"))
    manager.enforce_authorization(Principal("admin", users["admin"], "admin"))
    assert manager.unlock_account("engineer") is True


# ---------------------------------------------------------------- password verification

def test_retired_and_malformed_hash_formats_fail_closed(db):
    import hashlib

    manager, _ = db
    static_salted = hashlib.sha256(("DrillMaster_2024_Salt" + "pw").encode()).hexdigest()
    assert manager._verify_password("pw", static_salted) is False
    assert manager._verify_password("pw", "$2b$12$not-a-valid-bcrypt-hash") is False
    assert manager._verify_password("pw", "") is False
    salt = "ab" * 8
    salted = "sha256:%s:%s" % (salt, hashlib.sha256((salt + "pw").encode()).hexdigest())
    assert manager._verify_password("pw", salted) is True  # development-only format


def test_salted_sha256_is_refused_in_production(monkeypatch):
    import hashlib

    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    salt = "cd" * 8
    salted = "sha256:%s:%s" % (salt, hashlib.sha256((salt + "pw").encode()).hexdigest())
    assert DatabaseManager()._verify_password("pw", salted) is False


def test_successful_login_upgrades_a_development_sha256_hash_to_bcrypt(db):
    import hashlib

    manager, path = db
    salt = "ef" * 8
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE users SET password_hash=? WHERE username='engineer'",
                           ("sha256:%s:%s" % (salt, hashlib.sha256((salt + "dev-pass-1").encode()).hexdigest()),))
    assert manager.authenticate_user("engineer", "dev-pass-1")
    stored = _rows(path, "SELECT password_hash FROM users WHERE username='engineer'")[0][0]
    assert stored.startswith("$2")
    assert manager.authenticate_user("engineer", "dev-pass-1")


def test_switching_user_works_while_a_restricted_principal_is_enforced(db, monkeypatch):
    """Login bookkeeping (throttle, last_login) runs in the system scope, so a
    viewer session can still sign in as another account."""
    manager, path = db
    users = dict(_rows(path, "SELECT username, id FROM users"))
    manager.enforce_authorization(Principal("viewer", users["viewer"], "viewer"))
    _fail(manager, 1)
    assert _rows(path, "SELECT COUNT(*) FROM login_throttle") == [(1,)]
    assert manager.authenticate_user("admin", ADMIN_PASSWORD)
    assert _rows(path, "SELECT COUNT(*) FROM login_throttle") == [(0,)]
    assert _rows(path, "SELECT last_login IS NOT NULL FROM users WHERE username='admin'") == [(1,)]
