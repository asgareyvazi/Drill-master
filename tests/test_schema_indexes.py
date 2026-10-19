"""Schema v6 secondary indexes: plan integrity and query-plan evidence (M43).

Query-plan assertions are structural (an index is used / a table is not fully
scanned); they never compare SQLite's full plan text or timings.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.database import Base, DatabaseManager
from core.schema_indexes import INDEX_PLAN, index_name

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("db_workload", ROOT / "tools" / "perf" / "db_workload.py")
workload = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workload)


# ---------------------------------------------------------------- plan integrity

def test_every_planned_index_targets_real_columns_and_is_registered():
    names = [index_name(table, columns) for table, columns, _ in INDEX_PLAN]
    assert len(names) == len(set(names))
    for table_name, columns, reason in INDEX_PLAN:
        table = Base.metadata.tables[table_name]
        assert set(columns) <= set(table.c.keys()), (table_name, columns)
        assert reason, "every index needs the access path it serves"
        registered = {i.name: tuple(c.name for c in i.columns) for i in table.indexes}
        assert registered[index_name(table_name, columns)] == columns


def test_no_planned_index_is_made_redundant_by_another():
    """A single-column index is redundant when another index on the same
    table starts with that column (the composite already serves it)."""
    by_table = {}
    for table, columns, _ in INDEX_PLAN:
        by_table.setdefault(table, []).append(columns)
    for table, entries in by_table.items():
        for columns in entries:
            for other in entries:
                if other is not columns and len(other) > len(columns):
                    assert other[:len(columns)] != columns, (table, columns, other)


def test_every_cascade_child_of_daily_reports_is_indexed():
    """Deleting a report scans each ON DELETE CASCADE child; all must be indexed."""
    leading = {(t, c[0]) for t, c, _ in INDEX_PLAN}
    missing = [
        table.name
        for table in Base.metadata.sorted_tables
        for fk in table.foreign_keys
        if fk.column.table.name == "daily_reports" and (table.name, fk.parent.name) not in leading
    ]
    assert missing == []


# ---------------------------------------------------------------- query plans

@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    directory = tmp_path_factory.mktemp("indexed")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(directory),
                       "DRILLMASTER_DB_PATH": str(directory / "plans.db"), "DRILLMASTER_AI_IMPORT": "0"}.items():
        mp.setenv(key, value)
    mp.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    ids = workload.build_dataset(manager, wells=2, reports_per_well=6)
    yield manager, Path(directory / "plans.db"), ids
    manager.close()
    mp.undo()


SCOPED_OPERATIONS = (
    "list_reports_by_well", "list_reports_by_section", "open_report_full_snapshot", "report_time_logs",
    "survey_by_well", "survey_by_report", "report_revisions", "approval_history", "audit_for_report",
    "recent_audit", "cost_totals", "latest_mud_report",
)


@pytest.mark.parametrize("operation", SCOPED_OPERATIONS)
def test_scoped_application_queries_do_not_scan_whole_tables(populated, operation):
    manager, path, ids = populated
    fn = workload._operations(manager, ids)[operation]
    statements = workload._capture_statements(manager, lambda: fn(0))
    assert statements, "the operation must issue SQL"
    plans = workload.explain(path, statements)
    assert [p for p in plans if p["full_scans"]] == []
    assert any("USING" in step and "INDEX ix_" in step for p in plans for step in p["plan"])


def test_report_list_is_ordered_by_the_composite_index_without_a_sort(populated):
    manager, path, ids = populated
    fn = workload._operations(manager, ids)["list_reports_by_well"]
    plan = workload.explain(path, workload._capture_statements(manager, lambda: fn(0)))[0]["plan"]
    assert any("ix_daily_reports_well_id_report_date" in step for step in plan)
    assert not any("TEMP B-TREE" in step for step in plan)


def test_without_the_indexes_the_same_queries_scan(tmp_path, monkeypatch):
    """A/B on the same code: dropping the ix_* indexes brings the scans back."""
    result = workload.run(wells=1, reports_per_well=4, repeats=1, warmup=1, drop_secondary_indexes=True)
    assert result["dropped_indexes"] == len(INDEX_PLAN)
    assert result["environment"]["secondary_indexes"] == 0
    assert result["operations"]["open_report_full_snapshot"]["full_scan_statements"] > 20
    indexed = workload.run(wells=1, reports_per_well=4, repeats=1, warmup=1)
    assert indexed["environment"]["secondary_indexes"] == len(INDEX_PLAN)
    assert indexed["operations"]["open_report_full_snapshot"]["full_scan_statements"] == 0
