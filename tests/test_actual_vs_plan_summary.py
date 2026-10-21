"""Direct tests for core.actual_vs_plan.summarize_actual_vs_plan (M43 closure).

The computation was extracted unchanged from DatabaseManager.get_actual_vs_plan
(which keeps the queries); these tests call it without a database. The
DB-level behaviour stays covered by test_engineering_completion,
test_m28_finance_safety_plan and test_m29_release_closure.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from core.actual_vs_plan import summarize_actual_vs_plan
from core.database import DatabaseManager


def _plan(days=None, depth=None):
    return NS(id=5, planned_total_days=days, planned_final_depth=depth)


def _report(depth=None, rop=None):
    return NS(depth_2400=depth, rop_meter=rop)


def test_activities_drive_planned_hours_depth_and_rop():
    activities = [{"planned_duration_hours": 10, "planned_depth_to": 300},
                  {"planned_duration_hours": 30, "planned_depth_to": 1000}]
    result = summarize_actual_vs_plan(_plan(days=99, depth=9999), activities,
                                      [_report(400, 20.0), _report(800, 30.0)], [], [], [])
    assert result["plan_id"] == 5 and result["reports"] == 2
    assert result["depth"]["planned"] == 1000 and result["depth"]["actual"] == 800
    assert result["hours"]["planned"] == 40
    assert result["rop"]["planned"] == pytest.approx(1000 / 40)
    assert result["rop"]["actual"] == pytest.approx(25.0)


def test_without_activities_the_plan_header_is_used():
    result = summarize_actual_vs_plan(_plan(days=2, depth=480), [], [_report(100)], [], [], [])
    assert result["hours"]["planned"] == 48
    assert result["depth"]["planned"] == 480
    assert result["rop"]["planned"] == pytest.approx(10.0)


def test_incomplete_activity_hours_stay_unknown_not_zero():
    activities = [{"planned_duration_hours": 10, "planned_depth_to": 300},
                  {"planned_duration_hours": None, "planned_depth_to": 600}]
    result = summarize_actual_vs_plan(_plan(days=5), activities, [], [], [], [])
    assert result["hours"]["planned"] is None
    assert result["rop"]["planned"] is None


def test_report_rop_wins_and_drilling_parameters_are_the_fallback():
    params = [NS(avg_rop=12.0), NS(avg_rop=-1.0), NS(avg_rop=None)]
    from_reports = summarize_actual_vs_plan(None, [], [_report(rop=40.0)], [], params, [])
    assert from_reports["rop"]["actual"] == pytest.approx(40.0)
    fallback = summarize_actual_vs_plan(None, [], [_report(rop=None), _report(rop=-3.0)], [], params, [])
    assert fallback["rop"]["actual"] == pytest.approx(12.0)  # negatives and blanks ignored


def test_no_plan_and_no_records_reports_unavailable_without_inventing_values():
    result = summarize_actual_vs_plan(None, [], [], [], [], [])
    assert result["plan_id"] is None and result["reports"] == 0
    for key in ("depth", "hours", "rop"):
        assert result[key]["planned"] is None and result[key]["actual"] is None
    assert {"currency", "currency_status"} <= set(result["cost"])


def test_database_manager_delegates_to_the_extracted_function(monkeypatch):
    import core.actual_vs_plan as module

    calls = []
    sentinel = {"delegated": True}
    monkeypatch.setattr(module, "summarize_actual_vs_plan", lambda *args: calls.append(args) or sentinel)

    class _Query:
        def filter(self, *a, **k):
            return self

        def join(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def one_or_none(self):
            return None

        def all(self):
            return []

    session = NS(query=lambda *a, **k: _Query(), close=lambda: None)
    manager = DatabaseManager.__new__(DatabaseManager)
    manager.create_session = lambda: session
    assert DatabaseManager.get_actual_vs_plan(manager, 1) is sentinel
    assert calls == [(None, [], [], [], [], [])]
