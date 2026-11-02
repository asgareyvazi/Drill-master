"""M95 - UX responsiveness: the measured hot paths and their behaviour-preserving fixes.

Measured by ``tools/quality/ux_responsiveness_m95.py`` (offscreen Linux, synthetic year; NOT a Windows
desktop measurement).  Two stalls were found and removed:

* Operational Analysis: ``ActivityMapper.map_activity`` per time-log row dominated (~90 %).  It is now
  memoised per call (``_map``) - these tests prove the memo returns exactly what the mapper returns and that a
  whole analysis is unchanged.
* W10 Planning first visit: the whole-well code statistics and FACT/PLAN chart were built and then
  immediately rebuilt for the pending section.  The whole-well pass is skipped only when a section follows in
  the same deferred apply; the shown rows must equal an explicit section reload, and a failed section step
  must leave the views empty rather than showing the previous well.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, time as dtime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import analysis_evidence as ev  # noqa: E402
from core import operational_analysis as oa  # noqa: E402
from core.activity_mapper import ActivityMapper  # noqa: E402
from core.database import DailyReport, Section, TimeLog24H  # noqa: E402
from document_link_fixtures import build_link_world  # noqa: E402
from synthetic_operations import make_file_database  # noqa: E402
from test_m70_selection_audit import _pump, window  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]


def _rows(table):
    return [[table.item(r, c).text() if table.item(r, c) else None for c in range(table.columnCount())]
            for r in range(table.rowCount())]


def _w10(win):
    return next(win.tab_widget.widget(i) for i in range(win.tab_widget.count())
                if type(win.tab_widget.widget(i)).__name__ == "PlanningWidget")


@pytest.mark.parametrize("code,description", [
    ("DRL", "Drilling 12 1/4 in hole"),            # exact code; description irrelevant
    ("DRL", "rig repair - waiting on parts"),      # exact code with a misleading description
    ("POOH", ""),
    ("", "Pull out of hole to change bit"),        # description decides
    ("ZZZ-UNKNOWN", "circulate and condition mud"),
    ("ZZZ-UNKNOWN", "rig repair"),
    ("", ""),
    ("6-2", "composite code"),
])
def test_memoised_mapping_equals_the_mapper(code, description):
    mapper, cache = ActivityMapper(), {}
    direct = ActivityMapper().map_activity(code, description)
    for _ in range(2):                              # second call is served from the cache
        got = oa._map(mapper, cache, code, description)
        assert (got.canonical_id, got.method) == (direct.canonical_id, direct.method)
        assert set(got._fields) == {"canonical_id", "method"}   # no description-dependent field leaks out


def test_a_whole_analysis_is_unchanged_by_the_memo(tmp_path, monkeypatch):
    db = make_file_database(tmp_path / "oa.db")
    ids = build_link_world(db)
    texts = ["Drilling ahead", "rig repair top drive", "circulate bottoms up", "", "wait on weather"]
    with db.session_scope() as s:
        for d in range(20):
            report = DailyReport(well_id=ids["alpha"], report_date=date(2025, 3, 1) + timedelta(days=d),
                                 report_number=300 + d, depth_0000=1000.0 + 30 * d, depth_2400=1030.0 + 30 * d)
            s.add(report)
            s.flush()
            for i, code in enumerate(["DRL", "RPR", "CIR", "", "ZZZ"]):
                s.add(TimeLog24H(report_id=report.id, time_from=dtime(i * 4), time_to=dtime(i * 4 + 4),
                                 duration=4.0, main_code=code, activity_description=texts[(i + d) % 5],
                                 is_npt=(code == "RPR")))
    scope = ev.AnalysisScope(well_id=ids["alpha"])
    memo = oa.analyze(db, scope)
    monkeypatch.setattr(oa, "_map", lambda mapper, cache, code, description: mapper.map_activity(code, description))
    plain = oa.analyze(db, scope)
    assert (memo.tables, memo.summary, memo.report_ids, memo.notes) == \
           (plain.tables, plain.summary, plain.report_ids, plain.notes)
    db.engine.dispose()


def _select(win, ids, well, section_id):
    from core.selection_manager import SelectionManager
    sm = SelectionManager()
    sm.select_well(well, {"name": "w"}, force=True)
    if section_id is not None:
        sm.select_section(section_id, {"name": "s"}, force=True)
    _pump(0.2)


def test_w10_first_visit_shows_exactly_the_section_rows(window):  # noqa: F811
    win, db, ids = window
    w10 = _w10(win)
    with db.session_scope() as s:
        section = s.query(Section).filter_by(well_id=ids["alpha"]).first().id
    win.tab_widget.setCurrentIndex(0)                       # W10 hidden: context is deferred
    _pump(0.1)
    _select(win, ids, ids["alpha"], section)
    assert w10._pending_well is not None and w10._pending_section[0] == section
    win.tab_widget.setCurrentWidget(w10)                    # first visit: deferred apply
    _pump(0.3)
    assert w10._pending_section is None and w10.save_context_ready()
    shown = (_rows(w10.code_tab.code_table), _rows(w10.well_plan_tab.fact_table),
             _rows(w10.well_plan_tab.plan_table))
    for sub in (w10.code_tab, w10.well_plan_tab):           # state on the widget whose methods run
        inner = getattr(sub, "_inner", sub)
        assert "current_well_id" not in vars(sub) or sub is inner, "wrapper must not shadow the inner state"
        assert (inner.current_well_id, inner.current_section_id) == (ids["alpha"], section)
    w10.code_tab.set_current_section(section)              # explicit reload = the pre-M95 final state
    w10.well_plan_tab.set_current_section(section)
    assert shown == (_rows(w10.code_tab.code_table), _rows(w10.well_plan_tab.fact_table),
                     _rows(w10.well_plan_tab.plan_table))
    assert shown[1], "the synthetic section has daily reports - the FACT table must not be empty"


def test_w10_without_a_section_still_loads_the_whole_well(window):  # noqa: F811
    win, db, ids = window
    w10 = _w10(win)
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    _select(win, ids, ids["alpha"], None)
    assert w10._pending_section is None
    win.tab_widget.setCurrentWidget(w10)
    _pump(0.3)
    assert w10.well_plan_tab.current_well_id == ids["alpha"] and w10.well_plan_tab.current_section_id is None
    assert _rows(w10.well_plan_tab.fact_table), "whole-well FACT rows expected"


def test_w10_failed_section_step_never_shows_the_previous_well(window, monkeypatch):  # noqa: F811
    win, db, ids = window
    w10 = _w10(win)
    with db.session_scope() as s:
        section = s.query(Section).filter_by(well_id=ids["alpha"]).first().id
    win.tab_widget.setCurrentWidget(w10)
    _select(win, ids, ids["alpha"], section)
    assert _rows(w10.well_plan_tab.fact_table)              # alpha's rows are on screen
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    _select(win, ids, ids["twin_1"], section)               # a section id arrives with the new well

    def boom(*_a):
        raise RuntimeError("synthetic section failure")
    monkeypatch.setattr(w10, "on_section_changed", boom)
    win.tab_widget.setCurrentWidget(w10)
    _pump(0.3)
    assert not w10.save_context_ready()                     # pending, not loaded
    assert w10.well_plan_tab.current_well_id == ids["twin_1"]
    assert _rows(w10.well_plan_tab.fact_table) == [] and _rows(w10.code_tab.code_table) == []
    monkeypatch.undo()
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    win.tab_widget.setCurrentWidget(w10)                    # retry on re-open succeeds
    _pump(0.3)
    assert w10.save_context_ready()


def test_the_measurement_tool_runs_and_reports_every_path(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run([sys.executable, str(ROOT / "tools/quality/ux_responsiveness_m95.py"),
                           "--days", "5", "--logs", "3", "--n", "1"],
                          capture_output=True, text=True, timeout=300, env=env, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr[-2000:]
    data = json.loads(proc.stdout)
    assert {"startup", "well_switch", "tab_visit", "oa_refresh", "catalogue", "export"} <= set(data)
    assert "not a Windows desktop measurement" in data["environment"]["note"]
    assert data["export"]["written"] is True and data["oa_refresh"]["daily_rows"] >= 5
    assert "PlanningWidget" in data["tab_visit"] and len(data["tab_visit"]) >= 15
