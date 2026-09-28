"""Credential/reset lifecycle regression tests. Random passwords are temporary test input."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys

import pytest

from core.credential_policy import (
    CredentialLifecycleError, _BOOTSTRAP_PASSWORD_ENV, _DEVELOPMENT_FIXTURE_PASSWORDS,
    runtime_environment, resolve_bootstrap_passwords,
)
from core.database import DatabaseManager, User, Company
from core.database_reset import reset_configured_database

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    for name in (*_BOOTSTRAP_PASSWORD_ENV.values(), "DRILLMASTER_ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DRILLMASTER_ENV", "development")
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(tmp_path / "state" / "live.db"))


def secret():
    return secrets.token_urlsafe(24)


def production(monkeypatch):
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    value = secret()
    monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", value)
    return value


def opened():
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    return manager


def user_count(manager):
    with manager.session_scope() as session:
        return session.query(User).count()


@pytest.mark.parametrize("mode", ["development", "dev", "test", "testing"])
def test_development_fresh_users_login_reopen_and_reset(monkeypatch, mode):
    monkeypatch.setenv("DRILLMASTER_ENV", mode)
    db = opened()
    assert user_count(db) == 3
    for role, password in _DEVELOPMENT_FIXTURE_PASSWORDS.items():
        assert db.authenticate_user(role, password)
    db.close()
    reopened = opened()
    assert user_count(reopened) == 3
    reopened.close()
    reset_configured_database()
    reset = opened()
    assert user_count(reset) == 3
    assert reset.authenticate_user("admin", _DEVELOPMENT_FIXTURE_PASSWORDS["admin"])
    reset.close()


def test_production_admin_only_hashes_login_and_safe_reopen(monkeypatch):
    password = production(monkeypatch)
    db = opened()
    assert user_count(db) == 1
    with db.session_scope() as session:
        assert session.query(Company).count() == 0
        stored = session.query(User).one().password_hash
        assert stored.startswith("$2b$12$") and stored != password
    assert db.authenticate_user("admin", password)
    db.close()
    monkeypatch.delenv("DRILLMASTER_ADMIN_PASSWORD")
    db = opened()  # bootstrap settings not required for existing safe users
    assert db.authenticate_user("admin", password)
    db.close()


def test_production_optional_accounts_are_explicit(monkeypatch):
    production(monkeypatch)
    for key in ("DRILLMASTER_USER_PASSWORD", "DRILLMASTER_VIEWER_PASSWORD"):
        monkeypatch.setenv(key, secret())
    db = opened()
    assert user_count(db) == 3
    for role, key in _BOOTSTRAP_PASSWORD_ENV.items():
        assert db.authenticate_user(role, os.environ[key])
    db.close()


@pytest.mark.parametrize("value", [None, "", "   ", "short", *_DEVELOPMENT_FIXTURE_PASSWORDS.values(), " ADMIN123 ", "x" * 73])
def test_production_bad_bootstrap_is_actionable_and_creates_no_users(monkeypatch, value, caplog):
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    if value is not None:
        monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", value)
    db = DatabaseManager()
    assert db.initialize() is False
    assert db.last_diagnostic["code"] in {"BOOTSTRAP_REQUIRED", "BOOTSTRAP_INVALID"}
    assert "unsafe development credential; reset" not in db.last_diagnostic["message"]
    assert user_count(db) == 0
    if value and value.strip():
        assert value not in caplog.text
    db.close()


@pytest.mark.parametrize("key", ["DRILLMASTER_USER_PASSWORD", "DRILLMASTER_VIEWER_PASSWORD"])
@pytest.mark.parametrize("value", ["", "user123"])
def test_explicit_optional_account_cannot_have_empty_or_fixture_secret(monkeypatch, key, value):
    production(monkeypatch)
    monkeypatch.setenv(key, value)
    with pytest.raises(CredentialLifecycleError):
        resolve_bootstrap_passwords()


def test_existing_unsafe_production_guard_survives_and_env_does_not_rotate(monkeypatch):
    db = opened()
    with db.session_scope() as session:
        session.query(User).filter_by(username="admin").one().username = "renamed-admin"
    db.close()
    production(monkeypatch)
    db = DatabaseManager()
    assert db.initialize() is False
    assert db.last_diagnostic["code"] == "UNSAFE_EXISTING_CREDENTIAL"
    assert "reset_database.py" in db.last_diagnostic["message"]
    assert db.authenticate_user("renamed-admin", _DEVELOPMENT_FIXTURE_PASSWORDS["admin"]) is None
    assert user_count(db) == 3
    db.close()


def test_production_reset_recovers_unsafe_database_and_restarts(monkeypatch, tmp_path, caplog):
    db = opened()
    assert user_count(db) == 3
    db.close()
    settings = tmp_path / "state" / "settings.json"
    settings.write_text('{"theme":"dark"}')
    password = production(monkeypatch)
    target = reset_configured_database()
    assert target.exists() and settings.exists()
    monkeypatch.delenv("DRILLMASTER_ADMIN_PASSWORD")
    db = opened()
    assert user_count(db) == 1
    assert db.authenticate_user("admin", password)
    for role, fixture in _DEVELOPMENT_FIXTURE_PASSWORDS.items():
        assert db.authenticate_user(role, fixture) is None
    with db.session_scope() as session:
        db._reject_unsafe_existing_credentials(session)
        assert session.query(Company).count() == 0
    db.close()
    assert password not in caplog.text
    assert password.encode() not in target.read_bytes()
    assert not list(target.parent.glob(".drillmaster-reset-*"))


@pytest.mark.parametrize("configured", [None, "", "admin123"])
def test_production_reset_preflight_keeps_existing_file_byte_for_byte(monkeypatch, configured):
    db = opened()
    target = Path(db.db_path)
    db.close()
    before = target.read_bytes()
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    if configured is not None:
        monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", configured)
    with pytest.raises(CredentialLifecycleError):
        reset_configured_database()
    assert target.read_bytes() == before
    assert not list(target.parent.glob(".drillmaster-reset-*"))


def test_default_cli_and_database_mode_are_both_production(monkeypatch):
    monkeypatch.delenv("DRILLMASTER_ENV")
    assert runtime_environment() == "production"
    result = subprocess.run([sys.executable, str(ROOT / "reset_database.py")], input="RESET\n", text=True,
                            capture_output=True, cwd=ROOT, env=os.environ.copy())
    assert result.returncode == 1
    assert "before data deletion" in result.stdout and "DRILLMASTER_ADMIN_PASSWORD" in result.stdout
    assert not Path(os.environ["DRILLMASTER_DB_PATH"]).exists()


def test_cli_secure_reset_from_other_working_directory_and_login(monkeypatch, tmp_path):
    password = production(monkeypatch)
    monkeypatch.delenv("DRILLMASTER_ENV")  # reproduce the original mismatch: no explicit mode
    result = subprocess.run([sys.executable, str(ROOT / "reset_database.py")], input="RESET\n", text=True,
                            capture_output=True, cwd=tmp_path, env=os.environ.copy())
    assert result.returncode == 0
    assert password not in result.stdout + result.stderr
    db = opened()
    assert db.authenticate_user("admin", password)
    db.close()


@pytest.mark.parametrize("mode", ["", "  ", "produciton", "staging"])
def test_unknown_or_empty_mode_fails_closed_before_creating_database(monkeypatch, mode):
    monkeypatch.setenv("DRILLMASTER_ENV", mode)
    db = DatabaseManager()
    assert not db.initialize()
    assert db.last_diagnostic["code"] == "ENVIRONMENT_INVALID"
    assert not Path(db.db_path).exists()


def test_alias_conflict_is_not_a_production_downgrade(monkeypatch):
    monkeypatch.setenv("DRILLMASTER_ENV", "development")
    monkeypatch.setenv("DRILLMASTER_ENVIRONMENT", "production")
    with pytest.raises(CredentialLifecycleError, match="conflict"):
        runtime_environment()


def test_alias_only_and_case_normalization(monkeypatch):
    monkeypatch.delenv("DRILLMASTER_ENV")
    monkeypatch.setenv("DRILLMASTER_ENVIRONMENT", " ProD ")
    assert runtime_environment() == "production"


def test_dotenv_is_not_silently_loaded(monkeypatch, tmp_path):
    monkeypatch.delenv("DRILLMASTER_ENV")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DRILLMASTER_ENV=development\n")
    assert runtime_environment() == "production"
    with pytest.raises(CredentialLifecycleError):
        resolve_bootstrap_passwords()


def test_bcrypt_required_before_reset_touches_existing_data(monkeypatch):
    db = opened()
    path = Path(db.db_path)
    db.close()
    before = path.read_bytes()
    production(monkeypatch)
    monkeypatch.setattr("core.database._BCRYPT_AVAILABLE", False)
    with pytest.raises(CredentialLifecycleError, match="bcrypt"):
        reset_configured_database()
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", ["initialize", "promote"])
def test_reset_preparation_or_promotion_failure_preserves_old_database(monkeypatch, failure):
    password = production(monkeypatch)
    db = opened()
    target = Path(db.db_path)
    db.close()
    if failure == "initialize":
        monkeypatch.setattr(DatabaseManager, "initialize", lambda self: False)
    else:
        def denied(*args):
            raise PermissionError("test: file open on Windows")
        monkeypatch.setattr("core.database_reset.os.replace", denied)
    with pytest.raises((RuntimeError, PermissionError)):
        reset_configured_database()
    with sqlite3.connect(target) as conn:
        stored = conn.execute("select password_hash from users where username='admin'").fetchone()[0]
    assert DatabaseManager()._verify_password(password, stored)
    assert not list(target.parent.glob(".drillmaster-reset-*"))


def test_reset_refuses_active_wal_reader(monkeypatch):
    production(monkeypatch)
    db = opened()
    path = db.db_path
    db.close()
    reader = sqlite3.connect(path)
    reader.execute("PRAGMA journal_mode=WAL")
    reader.execute("BEGIN")
    reader.execute("select * from users").fetchall()
    try:
        with pytest.raises((RuntimeError, sqlite3.OperationalError)):
            reset_configured_database()
        assert reader.execute("select count(*) from users").fetchone()[0] == 1
    finally:
        reader.close()


def test_first_run_overrides_not_retained_or_written_to_environment(monkeypatch, caplog):
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    password = secret()
    db = DatabaseManager(bootstrap_passwords={"admin": password})
    assert db.initialize()
    assert db._bootstrap_override is None
    assert "DRILLMASTER_ADMIN_PASSWORD" not in os.environ
    assert db.authenticate_user("admin", password)
    db.close()
    assert password not in caplog.text


def test_existing_legacy_hash_rejected_without_plaintext_logging(monkeypatch, caplog):
    db = opened()
    temporary = secret()
    with db.session_scope() as session:
        session.query(User).filter_by(username="admin").one().password_hash = temporary
    db.close()
    production(monkeypatch)
    db = DatabaseManager()
    assert not db.initialize()
    assert db.last_diagnostic["code"] == "UNSAFE_EXISTING_CREDENTIAL"
    assert temporary not in caplog.text + json.dumps(db.last_diagnostic)
    db.close()


def test_same_paths_for_windows_configuration(monkeypatch, tmp_path):
    from core.runtime_config import database_path
    monkeypatch.delenv("DRILLMASTER_DATA_DIR")
    monkeypatch.delenv("DRILLMASTER_DB_PATH")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Windows User" / "AppData" / "Local"))
    monkeypatch.setattr("core.runtime_config.platform.system", lambda: "Windows")
    assert Path(database_path()) == tmp_path / "Windows User" / "AppData" / "Local" / "DrillMaster" / "drillmaster.db"
    assert DatabaseManager().db_path == database_path()


def test_actual_startup_bootstrap_method_honors_environment_without_dialog(monkeypatch):
    # Execute the actual method against a protocol owner, not native Qt.
    from types import SimpleNamespace
    from core.credential_policy import is_production_environment
    production(monkeypatch)
    tree = ast.parse((ROOT / "app.py").read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_first_run_bootstrap")
    scope = {"os": os, "is_production_environment": is_production_environment}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "app.py", "exec"), scope)
    owner = SimpleNamespace(_needs_first_run_bootstrap=lambda: True)
    assert scope[method.name](owner) is True
    assert owner._bootstrap_credentials is None


def test_gui_offline_reset_is_truthful_and_first_run_does_not_export_secrets():
    settings = (ROOT / "dialogs/settings_dialog.py").read_text()
    assert "reset_db.py" not in settings
    assert "No data has been changed" in settings and "python reset_database.py" in settings
    app = (ROOT / "app.py").read_text()
    assert 'os.environ["DRILLMASTER_ADMIN_PASSWORD"] =' not in app
    assert 'if "DRILLMASTER_ENV" not in os.environ' in app  # explicit empty mode is not overwritten
    dialog = (ROOT / "dialogs/bootstrap_dialog.py").read_text()
    assert "validate_production_password(value)" in dialog
    assert 'role != "admin"' in dialog


@pytest.mark.parametrize("state", ["absent", "no_users_table", "empty_users", "existing_user", "corrupt"])
def test_actual_first_run_detection_distinguishes_empty_from_existing(tmp_path, state):
    path = tmp_path / "first-run.db"
    if state == "corrupt":
        path.write_bytes(b"not a sqlite database")
    elif state != "absent":
        connection = sqlite3.connect(path)
        try:
            if state != "no_users_table":
                connection.execute("create table users (id integer)")
                if state == "existing_user":
                    connection.execute("insert into users values (1)")
            connection.commit()
        finally:
            connection.close()
    tree = ast.parse((ROOT / "app.py").read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_needs_first_run_bootstrap")
    method.decorator_list = []
    scope = {"Path": Path, "database_path": lambda: str(path)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "app.py", "exec"), scope)
    assert scope[method.name]() is (state in {"absent", "no_users_table", "empty_users"})
    if path.exists():
        path.rename(tmp_path / "probe-closed.db")  # actual Windows run also exercises handle closure


@pytest.mark.parametrize("initialize_ok", [True, False])
def test_package_smoke_never_targets_operator_database_or_retains_test_mode(monkeypatch, initialize_ok):
    # Actual smoke coordinator, with module/DB protocol probes (not a bundle/Qt run).
    import importlib
    import logging
    from types import SimpleNamespace
    production(monkeypatch)
    monkeypatch.setenv("DRILLMASTER_ENVIRONMENT", "production")
    previous = dict(os.environ)
    observed = {}
    class Probe:
        schema_version = 2
        def initialize(self):
            observed["path"] = DatabaseManager().db_path
            assert observed["path"] != previous["DRILLMASTER_DB_PATH"]
            assert runtime_environment() == "test"
            assert resolve_bootstrap_passwords() == _DEVELOPMENT_FIXTURE_PASSWORDS
            return initialize_ok
        def create_session(self):
            return SimpleNamespace(execute=lambda sql: SimpleNamespace(scalar=lambda: 2), close=lambda: None)
        def close(self):
            observed["closed"] = True
    tree = ast.parse((ROOT / "app.py").read_text())
    method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_package_smoke")
    scope = {"os": os, "Path": Path, "DatabaseManager": Probe, "logger": logging.getLogger(__name__)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "app.py", "exec"), scope)
    monkeypatch.setattr(importlib, "import_module", lambda name: None)
    assert scope[method.name]() == (0 if initialize_ok else 1)
    assert observed["closed"] and not Path(observed["path"]).parent.exists()
    for key in ("DRILLMASTER_ENV", "DRILLMASTER_ENVIRONMENT", "DRILLMASTER_DB_PATH", "DRILLMASTER_ADMIN_PASSWORD"):
        assert os.environ[key] == previous[key]
