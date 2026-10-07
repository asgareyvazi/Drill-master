"""Disposable-database acceptance for fresh init and historical schema upgrades."""
from __future__ import annotations

import sqlite3
import pytest
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.schema import CreateTable

from core.database import Base, DatabaseManager


V1_COLUMNS = {
    "drilling_parameters": {"pump_liner_size"},
    "service_companies": {"npt_hours", "hole_section", "duration_day", "condition", "issue"},
    "mud_reports": {"calcium", "kcl", "mbt", "pf_mf", "total_hardness", "flowline_temp", "pit_volumes_json"},
    "fuel_water_inventory": {
        "fuel_camp_consumed", "fuel_camp_stock", "fuel_camp_received",
        "dw_consumed", "dw_stock", "dw_received",
    },
    "daily_reports": {"forecast", "wellbore_id", "mw_pcf"},
    "sections": {"wellbore_id"},
    "wells": {"drilling_engineer"},
}


def _split_definitions(body: str) -> list[str]:
    pieces, start, depth, quote = [], 0, 0, None
    i = 0
    while i < len(body):
        char = body[i]
        if quote:
            if char == quote:
                if i + 1 < len(body) and body[i + 1] == quote:
                    i += 1
                else:
                    quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            pieces.append(body[start:i])
            start = i + 1
        i += 1
    pieces.append(body[start:])
    return pieces


def _build_old_schema(path, version: int) -> None:
    """Build an isolated v1/v2 database from ORM DDL minus later columns."""
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=OFF")
    for table in Base.metadata.sorted_tables:
        if version <= 2 and table.name == "wellbores":
            continue
        sql = str(CreateTable(table).compile(dialect=sqlite_dialect()))
        removed = set(V1_COLUMNS.get(table.name, set())) if version == 1 else set()
        if version <= 2:
            removed.update({"wellbore_id"}) if table.name in {"sections", "daily_reports"} else None
        if version < 4 and table.name == "daily_reports":
            removed.add("mw_pcf")
        if removed:
            open_paren, close_paren = sql.index("("), sql.rindex(")")
            prefix, body, suffix = sql[:open_paren], sql[open_paren + 1:close_paren], sql[close_paren:]
            definitions = [
                definition for definition in _split_definitions(body)
                if not any(column in definition for column in removed)
            ]
            sql = prefix + "(" + ",".join(definitions) + suffix
        connection.execute(sql)
    connection.execute("CREATE TABLE schema_version (version INTEGER NOT NULL, applied_at DATETIME NOT NULL)")
    connection.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, CURRENT_TIMESTAMP)", (version,))
    connection.execute("INSERT INTO companies(name, code) VALUES (?, ?)", ("M42 Migration", "M42"))
    company_id = connection.execute("SELECT id FROM companies").fetchone()[0]
    connection.execute("INSERT INTO projects(company_id, name, code) VALUES (?, ?, ?)", (company_id, "Legacy", "LEG"))
    project_id = connection.execute("SELECT id FROM projects").fetchone()[0]
    connection.execute("INSERT INTO wells(project_id, name, code) VALUES (?, ?, ?)", (project_id, "Legacy Well", "LW"))
    well_id = connection.execute("SELECT id FROM wells").fetchone()[0]
    connection.execute("INSERT INTO sections(well_id, name) VALUES (?, ?)", (well_id, "12-1/4"))
    section_id = connection.execute("SELECT id FROM sections").fetchone()[0]
    connection.execute(
        "INSERT INTO daily_reports(well_id, section_id, report_date, report_number) VALUES (?, ?, ?, ?)",
        (well_id, section_id, "2024-01-02", 7),
    )
    connection.commit()
    connection.close()


def _configure(tmp_path, monkeypatch, db_path):
    monkeypatch.setenv("DRILLMASTER_ENV", "test")
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(db_path))
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "0")


def test_fresh_initialization_reopen_wal_foreign_keys_and_schema_version(tmp_path, monkeypatch):
    path = tmp_path / "fresh.sqlite"
    _configure(tmp_path, monkeypatch, path)
    for _ in range(2):
        manager = DatabaseManager()
        assert manager.initialize(), manager.last_diagnostic
        try:
            raw = manager.engine.raw_connection()
            try:
                assert raw.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
                assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1
                assert raw.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
                assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
            finally:
                raw.close()
        finally:
            manager.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(4,)]


@pytest.mark.parametrize("old_version", [1, 2])
def test_legacy_schema_upgrade_preserves_rows_unknowns_indexes_and_is_idempotent(
    tmp_path, monkeypatch, old_version
):
    path = tmp_path / f"v{old_version}.sqlite"
    _configure(tmp_path, monkeypatch, path)
    _build_old_schema(path, old_version)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    manager.close()
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    manager.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(4,)]
        assert connection.execute("SELECT name FROM wells WHERE id=1").fetchone() == ("Legacy Well",)
        assert connection.execute("SELECT report_number FROM daily_reports WHERE id=1").fetchone() == (7,)
        assert connection.execute("SELECT wellbore_id FROM sections WHERE id=1").fetchone() == (None,)
        assert connection.execute("SELECT wellbore_id, mw_pcf FROM daily_reports WHERE id=1").fetchone() == (None, None)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        foreign_keys = connection.execute("PRAGMA foreign_key_list(sections)").fetchall()
        assert sum(row[2] == "wellbores" for row in foreign_keys) == 1
        expected_indexes = {index.name for index in Base.metadata.tables["daily_reports"].indexes if index.name}
        installed_indexes = {row[1] for row in connection.execute("PRAGMA index_list(daily_reports)")}
        assert expected_indexes <= installed_indexes
        if old_version == 1:
            assert "drilling_engineer" in {row[1] for row in connection.execute("PRAGMA table_info(wells)")}
            assert "fuel_camp_stock" in {row[1] for row in connection.execute("PRAGMA table_info(fuel_water_inventory)")}


def test_v3_upgrade_adds_nullable_header_measurement_without_backfill(tmp_path, monkeypatch):
    path = tmp_path / "v3.sqlite"
    _configure(tmp_path, monkeypatch, path)
    _build_old_schema(path, 3)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE schema_version SET version=3")
        # v3 already contains the row, but its v4 header reading is unknown.
        assert connection.execute("SELECT report_number FROM daily_reports").fetchone() == (7,)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    manager.close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(4,)]
        assert connection.execute("SELECT mw_pcf FROM daily_reports").fetchone() == (None,)
        assert connection.execute("SELECT report_number FROM daily_reports").fetchone() == (7,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
