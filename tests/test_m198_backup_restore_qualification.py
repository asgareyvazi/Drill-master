"""M198: migration, backup and restore qualification for the M171-M190 data on real temporary database files.

Real SQLite files in tmp_path. An old (v5) database without the M157 / M178 tables is upgraded in place; the
M173-M190 records (saved trajectory views, published tubular sets with their storage guards, calculation cases with
library snapshots) are backed up with the real BackupService, changed afterwards and restored with the real
RestoreService. After the restore every record verifies again, the guards are present, and the later changes are
gone. SYNTHETIC data only.
"""
from __future__ import annotations

import sqlite3

import pytest

from core import calculation_cases as cc
from core import db_maintenance as dm
from core import storage_guards
from core import trajectory_views as tv
from core.engineering import reference_binding as rb
from core.engineering import tubular_reference as tr
from tests.test_database_migration_acceptance import _build_old_schema
from tests.test_m70_integrity import NEW_TABLES, _open, _seed
from tests.test_m72_surveys_solver import J_STATIONS

PROV = tr.Provenance(origin="user", entered_by="synthetic-tester")
M171_TABLES = ("tubular_reference_sets", "tubular_reference_items", "trajectory_view_revisions")
TUBULAR_GUARDS = {name for name in storage_guards.trigger_statements() if name.startswith("trg_tubular_")}


class _Admin:
    user_id, username = 1, "synthetic-admin"

    def has_permission(self, name):
        return name == dm.MAINTAIN_DATABASE


def _triggers(path):
    with sqlite3.connect(path) as connection:
        return {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}


def _tables(path):
    with sqlite3.connect(path) as connection:
        return {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


@pytest.fixture
def upgraded(tmp_path, monkeypatch):
    path = tmp_path / "live.sqlite"
    _build_old_schema(path, 5)
    with sqlite3.connect(path) as connection:
        for table in NEW_TABLES + ("survey_revisions",) + M171_TABLES:
            connection.execute(f"DROP TABLE IF EXISTS {table}")
    assert not set(M171_TABLES) & _tables(path)
    monkeypatch.setenv("DRILLMASTER_BACKUP_DIR", str(tmp_path / "backups"))
    manager = _open(path, tmp_path, monkeypatch)
    yield manager, path, tmp_path
    manager.close()


def test_an_old_database_gains_the_new_tables_and_guards_and_keeps_its_rows(upgraded):
    manager, path, _tmp = upgraded
    assert set(M171_TABLES) <= _tables(path)
    assert TUBULAR_GUARDS and TUBULAR_GUARDS <= _triggers(path)
    assert {n for n in storage_guards.trigger_statements() if n.startswith("trg_trajectory_view")} <= _triggers(path)
    ids = _seed(manager)                                   # the upgraded file is fully usable
    assert manager.save_survey_points([dict(s, well_id=ids["A"][0]) for s in J_STATIONS])


def test_backup_and_restore_bring_back_exactly_the_snapshot_and_every_record_verifies(upgraded):
    manager, path, tmp = upgraded
    ids = _seed(manager)
    well = ids["A"][0]
    assert manager.save_survey_points([dict(s, well_id=well) for s in J_STATIONS])
    view = tv.save_view(manager, well, "SYN qualified view")
    set_id = tr.create_set(manager, "SYN library")["id"]
    tr.add_item(manager, set_id, tr.TubularSpec("DP", "SYN-Q-DP", PROV, nominal_od_in=4.871, id_in=4.013))
    tr.publish_set(manager, set_id)
    row = next(r for r in tr.search(manager) if r["spec"].designation == "SYN-Q-DP")
    binding = rb.make_binding(tr.reference_snapshot(row), rb.PIPE_COMPONENT_FIELDS)
    case = cc.save_case(manager, calculator="Weight", name="SYN qualified case", well_id=well,
                        inputs={"extra:pipes": {"value": [{"od": 4.871, "id": 4.013, rb.BINDING_KEY: binding}]}},
                        results={"x": {"value": 1}})

    backups = dm.BackupService(manager, tmp / "backups")
    snapshot = backups.create_backup(_Admin())
    assert snapshot.ok, snapshot

    # Changes after the backup: a revision of the view and a second library version.
    tv.revise_view(manager, view["view_key"], expected_revision=1, settings={"unit": "ft"}, note="later")
    later = tr.create_set(manager, "SYN library")["id"]
    tr.publish_set(manager, later)

    result = dm.RestoreService(manager, backups, drain_timeout=0.5, lock_timeout=0.5).restore(
        snapshot.path, _Admin(), confirmed=True)
    assert result.ok and result.safety_copy, result

    assert TUBULAR_GUARDS <= _triggers(path)
    heads = tv.list_views(manager, well)
    assert [(h["name"], h["revision"]) for h in heads] == [("SYN qualified view", 1)]
    assert tv.get_view(manager, view["id"])["integrity"] == "VERIFIED"
    assert [s["version"] for s in tr.list_sets(manager) if s["name"] == "SYN library"] == [1]
    stored = cc.get_case(manager, case["id"])["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY]
    assert stored == binding and tr.verify_snapshot(stored["snapshot"]) == []
    assert [r["state"] for r in rb.drift_report(manager, cc.get_case(manager, case["id"])["inputs"])] == [rb.MATCH]
    with sqlite3.connect(path) as connection:                    # the restored published set is still guarded
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE tubular_reference_sets SET notes = 'x' WHERE id = ?", (set_id,))
