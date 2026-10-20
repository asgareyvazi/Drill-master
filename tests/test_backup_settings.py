"""Automatic-backup settings: one resolved source of truth (M43 release hardening).

Before this, the Settings dialog saved ``backup/enabled`` and ``backup/path``
that nothing read, while the scheduler ran from environment variables only.
Every database here is a temporary synthetic file under pytest's tmp_path.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core import db_maintenance as dm
from core import sqlite_connection
from core.database import Company, DatabaseManager, Project, Well

ROOT = Path(__file__).resolve().parents[1]


class Principal:
    def __init__(self, *permissions, user_id=1, username="synthetic-admin"):
        self.permissions, self.user_id, self.username = set(permissions), user_id, username

    def has_permission(self, name):
        return name in self.permissions


ADMIN = Principal(dm.MAINTAIN_DATABASE)
ENV_KEYS = (dm.DIR_ENV, dm.KEEP_ENV, dm.INTERVAL_ENV)


@pytest.fixture()
def data(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("DRILLMASTER_ENV", "test")
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(data))
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(data / "live.db"))
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "0")
    for key in ("DRILLMASTER_ENVIRONMENT", sqlite_connection.BUSY_TIMEOUT_ENV, *ENV_KEYS):
        monkeypatch.delenv(key, raising=False)
    return data


@pytest.fixture()
def manager(data):
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    with manager.session_scope() as session:
        company = Company(name="Synthetic Co", code="SYN-CO")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Synthetic Project", code="SYN-PR")
        session.add(project)
        session.flush()
        session.add(Well(project_id=project.id, name="Synthetic Well", code="SYN-W1"))
    yield manager
    manager.close()


def _saved(**values):
    return {dm.SETTINGS_KEYS[name]: value for name, value in values.items()}


# ---------------------------------------------------------------- resolution and precedence

def test_defaults_match_the_behaviour_that_shipped(data):
    resolved = dm.resolve_backup_settings({})
    assert resolved.enabled is True  # the scheduler always ran by default; the old checkbox said "off"
    assert resolved.directory == (data / "backups").resolve()
    assert (resolved.interval_minutes, resolved.keep) == (dm.DEFAULT_INTERVAL_MINUTES, dm.DEFAULT_KEEP)
    assert resolved.schedule_seconds == dm.DEFAULT_INTERVAL_MINUTES * 60
    assert resolved.locked == {} and resolved.warnings == ()


def test_saved_settings_are_applied(data, tmp_path):
    folder = tmp_path / "second-disk" / "drillmaster-backups"
    resolved = dm.resolve_backup_settings(_saved(enabled="true", directory=str(folder),
                                                 interval_minutes="45", keep=3))
    assert (resolved.enabled, resolved.directory, resolved.interval_minutes, resolved.keep) == (
        True, folder.resolve(), 45, 3)
    assert resolved.schedule_seconds == 45 * 60
    assert not folder.exists()  # resolving settings has no side effects


def test_disabling_stops_scheduling_but_keeps_the_other_values(data):
    resolved = dm.resolve_backup_settings(_saved(enabled=False, interval_minutes=60, keep=4))
    assert resolved.enabled is False and resolved.schedule_seconds == 0
    assert (resolved.interval_minutes, resolved.keep) == (60, 4)


def test_environment_overrides_saved_settings_and_locks_the_field(data, tmp_path, monkeypatch):
    env_folder, saved_folder = tmp_path / "env-backups", tmp_path / "saved-backups"
    monkeypatch.setenv(dm.DIR_ENV, str(env_folder))
    monkeypatch.setenv(dm.KEEP_ENV, "7")
    monkeypatch.setenv(dm.INTERVAL_ENV, "15")
    resolved = dm.resolve_backup_settings(_saved(directory=str(saved_folder), keep=2, interval_minutes=90))
    assert (resolved.directory, resolved.keep, resolved.interval_minutes) == (env_folder.resolve(), 7, 15)
    assert resolved.locked == {"directory": dm.DIR_ENV, "keep": dm.KEEP_ENV, "interval_minutes": dm.INTERVAL_ENV}


def test_environment_interval_zero_disables_and_locks_enabled(data, monkeypatch):
    monkeypatch.setenv(dm.INTERVAL_ENV, "0")
    resolved = dm.resolve_backup_settings(_saved(enabled=True))
    assert resolved.enabled is False and resolved.schedule_seconds == 0
    assert resolved.locked["enabled"] == dm.INTERVAL_ENV


def test_legacy_keys_that_were_never_applied_are_ignored(data, tmp_path):
    legacy = {"backup/enabled": False, "backup/path": str(tmp_path / "legacy")}
    assert set(legacy) == set(dm.LEGACY_SETTINGS_KEYS)
    resolved = dm.resolve_backup_settings(legacy)
    # a saved "off" from the old dead checkbox must not silently switch backups off
    assert resolved.enabled is True and resolved.directory == (data / "backups").resolve()
    assert resolved.warnings == ()


@pytest.mark.parametrize("name, value", [
    ("interval_minutes", 4), ("interval_minutes", 1441), ("interval_minutes", "abc"),
    ("interval_minutes", 2.5), ("interval_minutes", True), ("keep", 0), ("keep", 1001),
    ("enabled", "maybe"), ("enabled", 2),
])
def test_invalid_saved_values_are_reported_and_never_applied(data, name, value):
    resolved = dm.resolve_backup_settings(_saved(**{name: value}))
    default = dm.resolve_backup_settings({})
    assert getattr(resolved, name) == getattr(default, name)
    assert len(resolved.warnings) == 1


def test_an_invalid_saved_folder_falls_back_visibly(data, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder")
    resolved = dm.resolve_backup_settings(_saved(directory=str(blocker / "sub")))
    assert resolved.directory == (data / "backups").resolve()
    assert len(resolved.warnings) == 1 and "default backup folder" in resolved.warnings[0]


def test_persisted_reader_takes_only_the_new_keys():
    class Store:
        values = {"database_backup/keep": "4", "backup/enabled": "false", "ui/theme": "Dark"}

        def contains(self, key):
            return key in self.values

        def value(self, key):
            return self.values[key]

    assert dm.persisted_backup_settings(Store()) == {"database_backup/keep": "4"}


# ---------------------------------------------------------------- folder validation

@pytest.mark.parametrize("raw, reason", [
    ("", "Choose"), ("   ", "Choose"), ("relative/backups", "absolute"),
    ("\\\\fileserver\\share\\backups", "Network"), ("//fileserver/share/backups", "Network"),
    ("\\\\?\\UNC\\fileserver\\share", "Network"),
])
def test_unsupported_folders_are_rejected_with_a_reason(raw, reason):
    with pytest.raises(ValueError, match=reason):
        dm.validate_backup_directory(raw)


def test_the_live_database_and_paths_through_files_are_rejected(tmp_path):
    live = tmp_path / "live.db"
    live.write_bytes(b"")
    with pytest.raises(ValueError, match="live database"):
        dm.validate_backup_directory(str(live), live)
    with pytest.raises(ValueError, match="file"):
        dm.validate_backup_directory(str(live / "backups"), live)


def test_local_folders_are_accepted_without_being_created(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    assert dm.validate_backup_directory(str(existing)) == existing.resolve()
    nested = tmp_path / "new" / "nested"
    assert dm.validate_backup_directory(str(nested), tmp_path / "live.db") == nested.resolve()
    assert not nested.exists()


# ---------------------------------------------------------------- no destructive cleanup on change

def test_changing_the_folder_never_touches_backups_in_the_old_folder(manager, tmp_path):
    old, new = tmp_path / "old-backups", tmp_path / "new-backups"
    first = dm.BackupService(manager, old, keep=1)
    made = [first.create_backup(ADMIN) for _ in range(2)]
    assert all(r.ok for r in made)
    before = sorted(p.name for p in old.iterdir())
    second = dm.BackupService(manager, new, keep=1)
    assert all(second.create_backup(ADMIN).ok for _ in range(2))
    assert sorted(p.name for p in old.iterdir()) == before


def test_lowering_retention_deletes_nothing_until_the_next_successful_backup(manager, tmp_path):
    folder = tmp_path / "backups"
    service = dm.BackupService(manager, folder, keep=5)
    assert all(service.create_backup(ADMIN).ok for _ in range(4))
    safety = service._create(dm.KIND_SAFETY)
    before = sorted(p.name for p in folder.glob("drillmaster_*.db"))
    lowered = dm.BackupService(manager, folder, keep=2)  # the next start after the setting changed
    assert sorted(p.name for p in folder.glob("drillmaster_*.db")) == before
    result = lowered.create_backup(ADMIN)
    assert result.ok and len(result.removed) == 3
    assert Path(safety.path).is_file()  # safety copies are never retention candidates


def test_disabled_settings_produce_a_scheduler_that_never_starts(manager, tmp_path):
    resolved = dm.resolve_backup_settings(_saved(enabled=False))
    scheduler = dm.BackupScheduler(dm.BackupService(manager, tmp_path / "b"), resolved.schedule_seconds)
    assert scheduler.start() is False
    assert scheduler.stop(timeout=1)


# ---------------------------------------------------------------- one backup path for the UI

def _calls_backup_to(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "backup_to"]


def test_no_application_module_copies_the_database_around_the_verified_service():
    """``DatabaseManager.backup_to`` has no permission check, manifest or audit entry.

    The Settings dialog and an unused main-window method used to call it, letting
    any logged-in role copy the whole database file anywhere.  Interactive
    backups must go through ``BackupService.create_backup`` instead.
    """
    offenders = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "tools/", ".venv/", "build/", "dist/")) or "/site-packages/" in rel:
            continue
        lines = _calls_backup_to(path)
        if lines:
            offenders[rel] = lines
    assert offenders == {}


def test_settings_dialog_routes_backup_now_through_the_main_window_service():
    source = (ROOT / "dialogs" / "settings_dialog.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_backup_database")
    names = {node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute)}
    strings = {node.value for node in ast.walk(method) if isinstance(node, ast.Constant)}
    assert "backup_database_now" in strings and "backup_to" not in names
    assert "backup/enabled" not in source and "backup/path" not in source
