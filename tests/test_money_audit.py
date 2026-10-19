"""Read-only monetary-column audit (tools/money/money_audit.py)."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from core import sqlite_connection
from core.database import DatabaseManager
from tools.money import money_audit


@pytest.fixture()
def seeded_db(tmp_path, monkeypatch):
    path = tmp_path / "money.db"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(tmp_path),
                       "DRILLMASTER_DB_PATH": str(path), "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    monkeypatch.delenv(sqlite_connection.BUSY_TIMEOUT_ENV, raising=False)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    manager.close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        project_id = connection.execute("SELECT id FROM projects LIMIT 1").fetchone()[0]
        connection.execute("UPDATE projects SET budget=4321.987, currency='usd' WHERE id=?", (project_id,))
        well_id = connection.execute(
            "INSERT INTO wells (project_id, name, code) VALUES (?, 'SYN-W1', 'SYNW1')", (project_id,)).lastrowid
        rows = [  # (planned, actual, variance, currency) - raw SQL bypasses the ORM listener
            (100.0, 75.25, 24.75, "USD"),            # consistent
            (0.3, 0.1, 0.19999999999999998, "USD"),  # float residue only
            (50.0, 60.0, 5.0, "EUR"),                # legacy inconsistent variance
            (12.345, None, None, None),              # inexact at cents, unknown actual, no currency
            (-10.0, 0.0, -10.0, "USD"),              # credit / negative
        ]
        connection.executemany(
            "INSERT INTO cost_records (well_id, category, planned_cost, actual_cost, variance, currency, vendor)"
            " VALUES (?, 'Rig', ?, ?, ?, ?, 'SyntheticVendorZ')", [(well_id, *row) for row in rows])
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    return path


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_audit_counts_facts_without_writing_or_printing_amounts(seeded_db, tmp_path, capsys):
    before = _sha256(seeded_db)
    report = money_audit.audit(seeded_db, scale=2)
    assert _sha256(seeded_db) == before

    planned = report["columns"]["cost_records.planned_cost"]
    assert planned["rows"] == 5 and planned["null"] == 0
    assert planned["inexact_at_scale_2"] == 1 and planned["negative"] == 1
    assert planned["currencies"] == {"USD": 3, "EUR": 1} and planned["currency_unknown"] == 1
    actual = report["columns"]["cost_records.actual_cost"]
    assert actual["null"] == 1 and actual["negative"] == 0
    budget = report["columns"]["projects.budget"]
    assert budget["inexact_at_scale_2"] >= 1 and budget["currencies"].get("USD", 0) >= 1
    assert report["columns"]["npt_reports.cost_impact"]["status"] == "present"

    variance = report["cost_records_variance"]
    assert variance["checked"] == 5
    assert variance["differs_exactly"] == 1  # only the legacy EUR row; the residue row matches
    assert variance["differs_at_cents"] == 1

    output = tmp_path / "report.json"
    assert money_audit.main(["--db", str(seeded_db), "--output", str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert json.loads(text) == report
    for secret in ("4321.987", "12.345", "75.25", "SyntheticVendorZ", "SYN-W1", str(seeded_db)):
        assert secret not in text
    assert _sha256(seeded_db) == before
    assert capsys.readouterr().out == ""


def test_audit_refuses_a_missing_database_without_creating_it(tmp_path):
    missing = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        money_audit.audit(missing)
    assert not missing.exists()


def test_audit_reports_absent_tables_and_columns(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)")
    connection.commit()
    connection.close()
    report = money_audit.audit(path)
    assert report["columns"]["projects.budget"] == {"status": "absent"}
    assert report["columns"]["cost_records.planned_cost"] == {"status": "absent"}
    assert report["cost_records_variance"] == {"status": "absent"}
