"""M136: security hardening — append-only audit log, owner-only files, session lock, security status.

Synthetic file databases only. The storage guards are exercised with raw SQL (every writer), the session lock
through the real login path (``authenticate_user``: bcrypt, failure counting, temporary lockout) and the Qt
controller through its widgets.
"""
from __future__ import annotations

import os
import sqlite3
import stat
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core import file_protection, security_posture, session_lock, storage_guards  # noqa: E402
from tests.test_data_layer_authorization import Principal  # noqa: E402
from synthetic_operations import make_file_database  # noqa: E402
from tabs.session_lock_ui import HIDDEN_PROPERTY  # noqa: E402

ADMIN_PASSWORD = "Synthetic-Admin-1!"
ENGINEER_PASSWORD = "Synthetic-Eng-1!"
POSIX = os.name == "posix"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path, monkeypatch):
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(tmp_path),
                       "DRILLMASTER_LOG_DIR": str(tmp_path / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(tmp_path / "backups")}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(session_lock.IDLE_ENV, raising=False)
    manager = make_file_database(tmp_path / "m136.db")
    yield manager
    manager.engine.dispose()


def _user(db, name):
    with db.session_scope() as session:
        return session.execute(text("SELECT id FROM users WHERE username=:u"), {"u": name}).scalar()


def _raw(db):
    return sqlite3.connect(db.db_path)


def _audit(db, action):
    with db.session_scope() as session:
        return session.execute(text("SELECT action, details FROM audit_logs WHERE action=:a ORDER BY id"),
                               {"a": action}).fetchall()


def _pump(seconds=0.05):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.005)


# ------------------------------------------------------------------ audit log append-only (storage)
def test_the_audit_log_refuses_update_delete_and_replace_for_every_writer(db):
    db.log_audit(action="m136_probe", entity_type="test", details="original")
    raw = _raw(db)
    try:
        row_id, details = raw.execute("SELECT id, details FROM audit_logs WHERE action='m136_probe'").fetchone()
        for statement in (f"UPDATE audit_logs SET details='rewritten' WHERE id={row_id}",
                          f"DELETE FROM audit_logs WHERE id={row_id}",
                          "DELETE FROM audit_logs",
                          f"INSERT OR REPLACE INTO audit_logs(id, action, details) VALUES ({row_id}, 'x', 'y')",
                          f"REPLACE INTO audit_logs(id, action, details) VALUES ({row_id}, 'x', 'y')"):
            with pytest.raises(sqlite3.IntegrityError, match="audit_logs: an audit record|audit_logs: a stored"):
                raw.execute(statement)
        raw.execute("INSERT INTO audit_logs(action, details) VALUES ('m136_append', 'appending still works')")
        raw.commit()
        assert raw.execute("SELECT details FROM audit_logs WHERE id=?", (row_id,)).fetchone()[0] == "original"
    finally:
        raw.close()
    assert _audit(db, "m136_append")


def test_the_system_scope_orm_path_cannot_rewrite_an_audit_record_either(db):
    from core.authorization import system_scope
    from core.database import AuditLog

    db.log_audit(action="m136_orm", entity_type="test", details="original")
    with system_scope():
        session = db.create_session()
        try:
            entry = session.query(AuditLog).filter(AuditLog.action == "m136_orm").one()
            entry.details = "rewritten"
            with pytest.raises(Exception, match="append-only"):
                session.commit()
            session.rollback()
        finally:
            session.close()
    assert _audit(db, "m136_orm")[0][1] == "original"


def test_an_existing_database_gets_the_audit_guards_on_its_next_start(db, tmp_path):
    names = sorted(n for n in storage_guards.trigger_statements() if n.startswith("trg_audit_log_"))
    assert names == ["trg_audit_log_append_only_v1", "trg_audit_log_nodelete_v1", "trg_audit_log_noreplace_v1"]
    raw = _raw(db)
    for name in names:
        raw.execute(f'DROP TRIGGER "{name}"')          # an M135-era database had none
    raw.commit()
    raw.close()
    db.engine.dispose()
    again = make_file_database(Path(db.db_path))
    try:
        with sqlite3.connect(again.db_path) as raw:
            assert set(names) <= storage_guards.installed(raw)
    finally:
        again.engine.dispose()


def test_deleting_a_well_still_works_and_keeps_its_audit_records(db):
    with db.session_scope() as session:
        q = session.execute
        q(text("INSERT INTO companies(name, code) VALUES ('Synthetic Co', 'M136')"))
        company = q(text("SELECT id FROM companies WHERE code='M136'")).scalar()
        q(text("INSERT INTO projects(company_id, name, code) VALUES (:c, 'P', 'M136P')"), {"c": company})
        project = q(text("SELECT id FROM projects WHERE code='M136P'")).scalar()
        q(text("INSERT INTO wells(project_id, name, code) VALUES (:p, 'SYN-136', 'M136W')"), {"p": project})
        well = q(text("SELECT id FROM wells WHERE code='M136W'")).scalar()
    db.enforce_authorization(Principal("admin", _user(db, "admin"), "admin"))   # the deletion is authorized
    with db.session_scope() as session:
        before = session.execute(text("SELECT id FROM audit_logs ORDER BY id")).scalars().all()
    assert db.delete_hierarchy_entity("well", well)
    with db.session_scope() as session:
        assert session.execute(text("SELECT COUNT(*) FROM wells WHERE id=:w"), {"w": well}).scalar() == 0
        after = session.execute(text("SELECT id FROM audit_logs ORDER BY id")).scalars().all()
    assert after[:len(before)] == before and len(after) > len(before)   # kept, and the deletion is audited


# ------------------------------------------------------------------ owner-only files
@pytest.mark.skipif(not POSIX, reason="POSIX permission bits")
def test_restrict_to_owner_sets_0600_and_0700_and_reports_it(tmp_path):
    path = tmp_path / "file.db"
    path.write_bytes(b"x")
    os.chmod(path, 0o644)
    assert file_protection.describe(str(path)) == "readable by group/others (0644)"
    assert file_protection.restrict_to_owner(str(path)) == "restricted to the owner (0600)"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert file_protection.restrict_to_owner(str(path)) == "owner-only (0600)"
    folder = tmp_path / "pkg"
    folder.mkdir(mode=0o755)
    os.chmod(folder, 0o755)
    assert file_protection.restrict_to_owner(str(folder)) == "restricted to the owner (0700)"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert file_protection.restrict_to_owner(str(tmp_path / "missing")) == "does not exist"


@pytest.mark.skipif(not POSIX, reason="POSIX permission bits")
def test_files_of_another_user_windows_and_refused_chmod_are_reported_not_changed(tmp_path, monkeypatch, caplog):
    path = tmp_path / "shared.db"
    path.write_bytes(b"x")
    os.chmod(path, 0o644)
    monkeypatch.setattr(file_protection.os, "getuid", lambda: os.stat(path).st_uid + 1)
    assert file_protection.restrict_to_owner(str(path)).startswith("not changed (owned by uid")
    monkeypatch.undo()
    monkeypatch.setattr(file_protection, "is_posix", lambda: False)
    assert file_protection.restrict_to_owner(str(path)) == file_protection.WINDOWS_NOTE
    assert file_protection.describe(str(path)) == file_protection.WINDOWS_NOTE
    monkeypatch.undo()

    def refuse(*_a):
        raise PermissionError("synthetic")
    monkeypatch.setattr(file_protection.os, "chmod", refuse)
    with caplog.at_level("WARNING"):
        outcome = file_protection.restrict_to_owner(str(path))
    assert outcome.startswith("not changed (PermissionError") and "Could not restrict" in caplog.text
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


@pytest.mark.skipif(not POSIX, reason="POSIX permission bits")
def test_the_live_database_is_owner_only_after_start(db):
    path = Path(db.db_path)
    os.chmod(path, 0o644)                             # e.g. created by an older build under a 022 umask
    db.engine.dispose()
    again = make_file_database(path)
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert again.file_protection[str(path)] == "restricted to the owner (0600)"
        for companion, outcome in again.file_protection.items():
            assert outcome.startswith(("restricted", "owner-only")), (companion, outcome)
    finally:
        again.engine.dispose()


# ------------------------------------------------------------------ session lock policy
@pytest.mark.parametrize("raw, minutes", [("", 0), ("15", 15), ("1440", 1440), ("0", 0), ("1441", 0),
                                          ("-5", 0), ("abc", 0), ("2.5", 0)])
def test_the_idle_limit_is_off_unless_a_valid_owner_value_is_set(raw, minutes):
    value, note = session_lock.idle_minutes({session_lock.IDLE_ENV: raw} if raw else {})
    assert value == minutes
    assert ("owner policy" in note) if not raw else (("after" in note) if minutes else ("off" in note))


def test_only_the_signed_in_users_password_unlocks_and_every_step_is_audited(db):
    lock = session_lock.SessionLock(db, _user(db, "engineer"), "engineer")
    with pytest.raises(ValueError):
        lock.lock("screensaver")
    assert lock.lock("manual") and not lock.lock("manual")     # idempotent: one audit record
    assert not lock.unlock("")
    assert not lock.unlock("wrong")
    assert not lock.unlock(ADMIN_PASSWORD)                      # another user's valid password
    assert lock.locked and lock.failures == 3
    assert lock.unlock(ENGINEER_PASSWORD) and not lock.locked
    assert [r[1] for r in _audit(db, "session_locked")] == [f"{session_lock.LOCK_VERSION}: manual"]
    assert _audit(db, "session_unlocked")[0][1].endswith("after 3 failed attempt(s)")
    assert len(_audit(db, "login_failed")) == 2                 # the empty password never reaches the check


def test_a_recreated_account_with_the_same_name_does_not_unlock_the_old_session(db):
    """The session belongs to a user record (id), not to a name: if the account behind the name is another record
    (deleted and recreated while the session was open), its valid password does not unlock."""
    old_session = session_lock.SessionLock(db, _user(db, "engineer"), "admin")   # name now held by another record
    old_session.lock("manual")
    assert not old_session.unlock(ADMIN_PASSWORD) and old_session.locked and old_session.failures == 1
    current = session_lock.SessionLock(db, _user(db, "admin"), "admin")      # the record that holds the name
    current.lock("manual")
    assert current.unlock(ADMIN_PASSWORD) and not current.locked


def test_repeated_failures_lock_the_account_so_even_the_right_password_waits(db, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_LOGIN_MAX_FAILURES", "3")
    lock = session_lock.SessionLock(db, _user(db, "engineer"), "engineer")
    lock.lock("idle")
    for _ in range(3):
        assert not lock.unlock("wrong")
    assert not lock.unlock(ENGINEER_PASSWORD) and lock.locked
    assert _audit(db, "login_locked") and _audit(db, "login_rejected_locked")


# ------------------------------------------------------------------ Qt controller
def _controller(app, db, environ=None, host=None):
    from tabs.session_lock_ui import SessionLockController
    host = host or QWidget()
    host.resize(640, 400)
    host.show()
    controller = SessionLockController(host, db, {"id": _user(db, "admin"), "username": "admin"}, environ or {})
    return host, controller


def test_locking_covers_the_window_and_only_the_right_password_reveals_it(app, db):
    host, controller = _controller(app, db)
    floating = QWidget()                                        # e.g. a floating panel or a tool window
    floating.setWindowTitle("synthetic floating window")
    floating.show()
    try:
        assert controller.idle_limit == 0 and controller.watcher is None
        assert controller.lock("manual")
        _pump()
        overlay, dialog = controller.overlay, controller.dialog
        assert overlay.isVisible() and overlay.geometry() == host.rect()
        assert dialog.isVisible() and dialog.windowModality() == Qt.ApplicationModal
        assert not floating.isVisible() and floating.property(HIDDEN_PROPERTY) is True
        host.resize(800, 500)
        _pump()
        assert overlay.geometry() == host.rect()                # follows the window
        dialog.reject()                                         # Escape: still locked
        _pump()
        assert dialog.isVisible() and controller.locked and "stays locked" in dialog.message.text()
        dialog.password.setText("wrong")
        dialog.unlock_btn.click()
        assert controller.locked and dialog.password.text() == "" and "1 failed attempt" in dialog.message.text()
        dialog.password.setText(ADMIN_PASSWORD)
        dialog.unlock_btn.click()
        _pump()
        assert not controller.locked and not overlay.isVisible() and controller.dialog is None
        assert floating.isVisible() and floating.property(HIDDEN_PROPERTY) is None
    finally:
        floating.close()
        floating.deleteLater()
        controller.shutdown()
        host.close()
        host.deleteLater()
        _pump()


class _RefusingHost(QWidget):
    def closeEvent(self, event):
        event.ignore()


def test_exit_uses_the_normal_close_path_and_a_refused_close_keeps_the_lock(app, db):
    host, controller = _controller(app, db, host=_RefusingHost())
    try:
        controller.lock("manual")
        controller.dialog.exit_btn.click()
        _pump()
        assert controller.locked and controller.dialog.isVisible() and host.isVisible()
    finally:
        controller.dialog.password.setText(ADMIN_PASSWORD)
        controller.dialog.unlock_btn.click()
        controller.shutdown()
        host.deleteLater()
        _pump()
    host2, controller2 = _controller(app, db)
    controller2.lock("manual")
    controller2.dialog.exit_btn.click()
    _pump()
    assert not host2.isVisible()
    controller2.shutdown()
    host2.deleteLater()
    _pump()


def test_the_idle_watcher_locks_after_the_limit_and_input_restarts_it(app, db):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    host, controller = _controller(app, db, {session_lock.IDLE_ENV: "1"})
    watcher = controller.watcher
    try:
        assert watcher.timer.interval() == 60_000 and watcher.timer.isActive()
        watcher.timer.stop()
        press = QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), QPointF(5, 5), Qt.LeftButton, Qt.LeftButton,
                            Qt.NoModifier)
        QApplication.sendEvent(host, press)
        assert watcher.timer.isActive()                         # input restarted the idle time
        watcher.idle.emit()                                     # the limit elapsed
        _pump()
        assert controller.locked and controller.state.reason == "idle" and watcher.paused
        watcher.timer.stop()
        QApplication.sendEvent(host, press)
        assert not watcher.timer.isActive()                     # no restart while locked
        controller.try_unlock(ADMIN_PASSWORD)
        assert not controller.locked and not watcher.paused and watcher.timer.isActive()
        assert _audit(db, "session_locked")[-1][1].endswith(": idle")
    finally:
        controller.shutdown()
        assert not watcher.timer.isActive()
        host.close()
        host.deleteLater()
        _pump()


# ------------------------------------------------------------------ security status
def test_the_security_status_reports_live_state_and_states_its_limits(app, db):
    from dialogs.security_status_dialog import SecurityStatusDialog

    db.enforce_authorization(Principal("admin", _user(db, "admin"), "admin"))
    dialog = SecurityStatusDialog(db, None, {})
    rows = {area: (status, detail) for area, status, detail in dialog.rows}
    assert dialog.table.rowCount() == len(dialog.rows)
    assert rows["Authorization in the data layer"] == (security_posture.PROVIDED,
                                                       "every write is checked for 'admin'")
    status, detail = rows["Audit log append-only (storage)"]
    assert status == security_posture.PROVIDED and "trg_audit_log_append_only_v1" in detail
    assert rows["Session lock"][0] == security_posture.PARTIAL and "owner policy" in rows["Session lock"][1]
    for area in ("Encryption at rest", "Tamper evidence against file access", "Signatures"):
        assert rows[area][0] == security_posture.NOT_PROVIDED
    if POSIX:
        assert rows["Database file permissions"] == (security_posture.PROVIDED, "owner-only (0600)")
    dialog.deleteLater()


def test_the_security_status_does_not_claim_what_is_missing(db, monkeypatch):
    raw = _raw(db)
    raw.execute('DROP TRIGGER "trg_audit_log_append_only_v1"')
    raw.commit()
    raw.close()
    monkeypatch.setattr(file_protection, "is_posix", lambda: False)
    rows = {area: (status, detail) for area, status, detail in security_posture.posture(db, {})}
    assert rows["Audit log append-only (storage)"][0] == security_posture.PARTIAL
    assert rows["Database file permissions"] == (security_posture.NOT_PROVIDED, file_protection.WINDOWS_NOTE)
    assert rows["Authorization in the data layer"][0] == security_posture.OFF
    rows = {a: s for a, s, _d in security_posture.posture(db, {session_lock.IDLE_ENV: "10"})}
    assert rows["Session lock"] == security_posture.PROVIDED
