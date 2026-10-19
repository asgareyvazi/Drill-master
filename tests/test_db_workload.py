"""The synthetic database workload tool (tools/perf/db_workload.py), M43.

Only behaviour is asserted (determinism, isolation, cleanup); timings are
evidence for docs/DATABASE_PERFORMANCE.md, never assertions.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("db_workload", ROOT / "tools" / "perf" / "db_workload.py")
workload = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workload)


def test_workload_is_deterministic_and_cleans_up(tmp_path, monkeypatch):
    import tempfile

    before = {p.name for p in Path(tempfile.gettempdir()).glob("drillmaster-workload-*")}
    first = workload.run(wells=1, reports_per_well=5, repeats=1, warmup=1)
    second = workload.run(wells=1, reports_per_well=5, repeats=1, warmup=1)
    assert first["rows_after_run"] == second["rows_after_run"]
    assert first["reports"] == 5 and set(first["operations"]) == set(workload.MEASURED_OPERATIONS)
    assert {p.name for p in Path(tempfile.gettempdir()).glob("drillmaster-workload-*")} == before


def test_workload_restores_the_process_environment(monkeypatch):
    import os

    monkeypatch.setenv("DRILLMASTER_DB_PATH", "/nonexistent/sentinel.db")
    monkeypatch.delenv("DRILLMASTER_DATA_DIR", raising=False)
    workload.run(wells=1, reports_per_well=2, repeats=1, warmup=1)
    assert os.environ["DRILLMASTER_DB_PATH"] == "/nonexistent/sentinel.db"
    assert "DRILLMASTER_DATA_DIR" not in os.environ


def test_every_measured_operation_reports_a_query_plan():
    result = workload.run(wells=1, reports_per_well=3, repeats=2, warmup=1)
    for name, data in result["operations"].items():
        assert data["runs"] >= 1 and data["median_ms"] >= 0, name
        assert data["statements"] >= 1 and data["plans"], name
        assert all(p["plan"] for p in data["plans"]), name
    assert result["environment"]["pragmas"]["foreign_keys"] == 1
    assert result["environment"]["database_used_bytes"] > 0
