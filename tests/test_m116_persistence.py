"""M116: persistence requalification - every column of every immutable table is classified, the survey results
hash is frozen for every writer (D32), legacy guards are replaced, explicit SQLite date adapters (D16), and a
failed guarded write rolls back the whole unit of work.  SYNTHETIC data, temporary file databases.
"""
from __future__ import annotations

import re
import sqlite3
import warnings
from datetime import date, datetime

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

from core import sqlite_connection, storage_guards
from core import survey_revisions as sr
from core.database import Base, SurveyRevision
from tests.test_m70_integrity import _open, _seed

ROWS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
        {"md": 600.0, "inc": 20.0, "azi": 357.0}, {"md": 900.0, "inc": 35.0, "azi": 10.0}]
FROZEN = {"directional_plan_revisions": storage_guards._PLAN_FROZEN,
          "calculation_cases": storage_guards._CASE_FROZEN,
          "calculation_source_links": storage_guards._LINK_FROZEN,
          "survey_revisions": storage_guards._SURVEY_FROZEN,
          "well_architecture_revisions": storage_guards._ARCH_FROZEN}
#: the only columns of an immutable table that may change, and the rule that governs them
MUTABLE_BY_RULE = {("directional_plan_revisions", "status"): "draft → approved → archived (trg_plan_revision_status)"}
REFUSED = (IntegrityError, OperationalError, DatabaseError, sqlite3.DatabaseError)


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m116.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _immutable_trigger(table):
    return next(s for n, s in storage_guards.trigger_statements().items() if "immutable" in n and f" ON {table} " in s)


def test_every_column_of_every_immutable_table_is_frozen_a_set_null_reference_or_ruled():
    unclassified = {}
    for table, frozen in FROZEN.items():
        trigger = _immutable_trigger(table)
        references = set(re.findall(r"NEW\.(\w+) IS NOT OLD\.\1 AND NOT \(NEW\.\1 IS NULL", trigger))
        for column in Base.metadata.tables[table].columns:
            name = column.name
            if name in frozen:
                assert f"NEW.{name} IS NOT OLD.{name}" in trigger
            elif name not in references and (table, name) not in MUTABLE_BY_RULE:
                unclassified.setdefault(table, []).append(name)
            if name in references:
                assert column.nullable and column.foreign_keys, (table, name)
    assert unclassified == {}


def test_d32_the_survey_results_hash_is_frozen_for_every_writer(env):
    manager, path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], ROWS, depth_datum="RKB", azimuth_reference="true")
    session = manager.create_session()
    try:
        with pytest.raises(REFUSED):                                         # ORM bulk update
            session.execute(update(SurveyRevision).where(SurveyRevision.id == rev["id"])
                            .values(results_sha256="0" * 64))
            session.flush()
        session.rollback()
        with pytest.raises(REFUSED):                                         # Core / text statement
            session.execute(text("UPDATE survey_revisions SET results_sha256=NULL WHERE id=:i"), {"i": rev["id"]})
        session.rollback()
        row = session.get(SurveyRevision, rev["id"])                         # ORM unit of work
        row.results_sha256 = "f" * 64
        with pytest.raises(REFUSED):
            session.flush()
        session.rollback()
    finally:
        session.close()
    manager.close()
    with sqlite3.connect(path) as raw:                                       # raw sqlite3 writer
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            raw.execute("UPDATE survey_revisions SET results_sha256='abc' WHERE id=?", (rev["id"],))
    manager.initialize()
    again = sr.get_revision(manager, rev["id"])
    assert again["results_sha256"] == rev["results_sha256"] and again["results_integrity"] == "VERIFIED"


def test_a_legacy_survey_guard_is_replaced_by_the_current_version(env):
    manager, path, _ids = env
    manager.close()
    current = f"trg_survey_revision_immutable_v{storage_guards.SURVEY_GUARD_VERSION}"
    with sqlite3.connect(path) as raw:
        old_columns = [c for c in storage_guards._SURVEY_FROZEN if c != "results_sha256"]
        raw.execute(f"DROP TRIGGER {current}")
        raw.execute("CREATE TRIGGER trg_survey_revision_immutable_v1 BEFORE UPDATE ON survey_revisions WHEN "
                    + " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in old_columns)
                    + " BEGIN SELECT RAISE(ABORT, 'legacy'); END")
    manager.initialize()                                                     # the normal start-up migration
    with sqlite3.connect(path) as raw:
        names = storage_guards.installed(raw)
    assert current in names and "trg_survey_revision_immutable_v1" not in names
    assert storage_guards.SURVEY_GUARD_VERSION == 2


def test_d16_explicit_date_adapters_store_the_same_text_and_raise_no_deprecation(tmp_path):
    assert sqlite3.adapters[(date, sqlite3.PrepareProtocol)] is sqlite_connection._adapt_date
    assert sqlite3.adapters[(datetime, sqlite3.PrepareProtocol)] is sqlite_connection._adapt_datetime
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with sqlite3.connect(tmp_path / "d16.sqlite") as raw:
            raw.execute("CREATE TABLE t (d TEXT, dt TEXT)")
            raw.execute("INSERT INTO t VALUES (?, ?)", (date(2026, 1, 2), datetime(2026, 1, 2, 3, 4, 5, 6)))
            stored = raw.execute("SELECT d, dt FROM t").fetchone()
    assert stored == ("2026-01-02", "2026-01-02 03:04:05.000006")              # = the former default adapters
    assert sqlite_connection.ADAPTER_VERSION == 1


def test_a_refused_write_rolls_back_the_whole_unit_of_work(env):
    manager, _path, ids = env
    rev = sr.save_revision(manager, ids["A"][0], ROWS, depth_datum="RKB", azimuth_reference="true")
    session = manager.create_session()
    try:
        session.execute(text("UPDATE wells SET name='SYN-CHANGED' WHERE id=:i"), {"i": ids["A"][0]})
        with pytest.raises(REFUSED):
            session.execute(text("UPDATE survey_revisions SET results_json='[]' WHERE id=:i"), {"i": rev["id"]})
        session.rollback()
        assert session.execute(text("SELECT name FROM wells WHERE id=:i"), {"i": ids["A"][0]}).scalar() != "SYN-CHANGED"
    finally:
        session.close()


def test_a_fresh_database_has_every_guard_foreign_keys_and_integrity(env):
    manager, path, _ids = env
    manager.close()
    with sqlite3.connect(path) as raw:
        names = storage_guards.installed(raw)
        assert set(storage_guards.trigger_statements()) <= names
        assert raw.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
    manager.initialize()
    with manager.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


MSE_LINEAGE = ("wellbore_id", "report_id", "input_source", "lineage_version")


def _rebuild_mse_without_lineage(path):
    """The mse_calculations table as it was before M104 (SQLite cannot drop FK columns)."""
    with sqlite3.connect(path) as con:
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='mse_calculations'").fetchone()[0]
        lines = [ln for ln in ddl.splitlines() if not any(c in ln for c in MSE_LINEAGE)]
        old_ddl = "\n".join(lines).replace("CREATE TABLE mse_calculations", "CREATE TABLE mse_old")
        old_ddl = old_ddl.replace("(id),\n)", "(id)\n)").rstrip()
        keep = [r[1] for r in con.execute("PRAGMA table_info(mse_calculations)") if r[1] not in MSE_LINEAGE]
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(old_ddl)
        con.execute(f"INSERT INTO mse_old ({', '.join(keep)}) SELECT {', '.join(keep)} FROM mse_calculations")
        con.execute("DROP TABLE mse_calculations")
        con.execute("ALTER TABLE mse_old RENAME TO mse_calculations")
        assert not set(MSE_LINEAGE) & {r[1] for r in con.execute("PRAGMA table_info(mse_calculations)")}


@pytest.mark.parametrize("database", ["fresh", "upgraded"])
def test_new_lineage_references_are_set_null_and_the_run_is_kept(env, database):
    """M104 added mse_calculations.wellbore_id/report_id (ON DELETE SET NULL) by ALTER TABLE on old databases."""
    from core.database import DailyReport, MSECalculationRecord
    from core.repositories.mse_repository import MSECalculationRepository

    manager, path, ids = env
    well, bore = ids["A"]
    if database == "upgraded":
        manager.close()
        _rebuild_mse_without_lineage(path)
        manager.initialize()                                  # additive migration adds the columns
    with manager.session_scope() as session:
        report = DailyReport(well_id=well, wellbore_id=bore, report_date=date(2026, 1, 2), report_number=1)
        session.add(report)
        session.flush()
        report_id = report.id
    inputs = {"wob_lbf": 25000.0, "rpm": 120.0, "torque_ft_lbf": 8000.0, "rop_ft_hr": 50.0, "bit_diameter_in": 8.5}
    outputs = {"mse_psi": 127997.67, "axial_term_psi": 440.6, "rotary_term_psi": 127557.07, "bit_area_in2": 56.745}
    run = MSECalculationRepository(manager).save_run(inputs=inputs, result_values=outputs, method="Teale",
                                                     label="SYN M116 MSE", well_id=well, wellbore_id=bore,
                                                     report_id=report_id)
    run_id = run                                              # save_run returns the new record id
    assert manager.delete_hierarchy_entity("report", report_id) is True     # audited service delete
    with manager.session_scope() as session:
        row = session.get(MSECalculationRecord, run_id)
        assert row is not None and row.report_id is None and row.wellbore_id == bore   # unknown, never re-pointed
    manager.close()
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("DELETE FROM wellbores WHERE id=?", (bore,))
        assert con.execute("SELECT wellbore_id, report_id, mse_psi FROM mse_calculations WHERE id=?",
                           (run_id,)).fetchone() == (None, None, 127997.67)
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    manager.initialize()


def test_the_report_unlink_scope_covers_exactly_the_set_null_report_references():
    from core.authorization import REPORT_DELETE_UNLINK
    from core.database import report_reference_action

    declared = {mapper.class_.__tablename__: frozenset({"report_id"}) for mapper in Base.registry.mappers
                if hasattr(mapper.class_, "report_id") and report_reference_action(mapper.class_) == "SET NULL"}
    assert declared == dict(REPORT_DELETE_UNLINK.tables) and declared        # a new one must be added on purpose


def test_d33_a_report_deleter_without_edit_rights_keeps_the_mse_run(tmp_path, monkeypatch):
    from sqlalchemy import text as sql

    from core.authorization import DELETE_REPORTS, AuthorizationError
    from core.repositories.mse_repository import MSECalculationRepository
    from tests.test_m96_persistence_audit import _open as open_as

    path = tmp_path / "m116-d33.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    well, bore = _seed(manager)["A"]
    with manager.session_scope() as session:
        session.execute(sql("INSERT INTO daily_reports(well_id, report_date, report_number) VALUES (:w, '2026-01-02', 1)"),
                        {"w": well})
        report = session.execute(sql("SELECT id FROM daily_reports WHERE well_id=:w"), {"w": well}).scalar()
    run = MSECalculationRepository(manager).save_run(
        inputs={"wob_lbf": 25000.0, "rpm": 120.0, "torque_ft_lbf": 8000.0, "rop_ft_hr": 50.0, "bit_diameter_in": 8.5},
        result_values={"mse_psi": 127997.67}, method="Teale", label="SYN D33", well_id=well, report_id=report)
    manager.close()
    deleter = open_as(path, tmp_path, monkeypatch, principal="viewer", permissions={DELETE_REPORTS: True})
    try:
        assert deleter.delete_hierarchy_entity("report", report) is True
        with pytest.raises(AuthorizationError):            # the unlink scope never authorizes a plain update
            with deleter.session_scope() as session:
                session.execute(sql("UPDATE mse_calculations SET input_source='x' WHERE id=:i"), {"i": run})
    finally:
        deleter.close()
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT well_id, report_id, mse_psi FROM mse_calculations WHERE id=?",
                           (run,)).fetchone() == (well, None, 127997.67)
        details = con.execute("SELECT details FROM audit_logs WHERE action='delete' AND entity_type='daily_report'"
                              ).fetchone()[0]
    assert '"references_unlinked": 1' in details
