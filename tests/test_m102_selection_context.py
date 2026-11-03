"""M102: SelectionManager context snapshot, period filter and relation-based resolution (SYNTHETIC data)."""
from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from core import selection_context as ctx
from core.selection_manager import ContextSnapshot, SelectionManager


@pytest.fixture
def sel():
    manager = SelectionManager()
    manager.clear()
    manager.select_period(None, None)
    events = []
    manager.context_changed.connect(events.append)
    manager.events = events
    yield manager
    manager.context_changed.disconnect(events.append)
    manager.clear()
    manager.select_period(None, None)


@pytest.fixture
def world():
    from document_link_fixtures import build_link_world
    from synthetic_operations import make_file_database
    with tempfile.TemporaryDirectory() as tmp:
        db = make_file_database(Path(tmp) / "m102_unit.db")
        ids = build_link_world(db)
        yield db, ids
        db.engine.dispose()


WELL = {"id": 7, "name": "SYN-W7", "rig_name": "SYN RIG 7", "project_id": 3, "company_id": 2}


def test_snapshot_carries_every_level_and_the_generation(sel):
    sel.select_well(7, WELL)
    sel.select_wellbore(11, {"id": 11, "name": "SYN-W7 OH"})
    sel.select_section(5, {"id": 5, "name": "SYN 8 1/2 in"})
    sel.select_report(9, {"report_number": 4, "report_date": datetime(2031, 7, 20, 6, 0)})
    snap = sel.snapshot()
    assert snap == ContextSnapshot(generation=snap.generation, company_id=2, project_id=3, well_id=7,
                                   well_name="SYN-W7", rig_name="SYN RIG 7", wellbore_id=11,
                                   wellbore_name="SYN-W7 OH", section_id=5, section_name="SYN 8 1/2 in",
                                   report_id=9, report_number=4, report_date="2031-07-20")
    assert snap.generation == sel.context_token()[0]
    assert [e.report_id for e in sel.events] == [None, None, None, 9]       # one snapshot per change
    assert sel.events[-1] == snap and snap.as_dict()["rig_name"] == "SYN RIG 7"


def test_a_well_switch_drops_every_child_level(sel):
    sel.select_full_context(7, 5, 9, well_data=WELL, section_data={"name": "S"},
                            report_data={"report_number": 1, "report_date": "2031-07-19"},
                            wellbore_id=11, wellbore_data={"name": "B"})
    sel.select_well(8, {"name": "SYN-W8"})
    snap = sel.snapshot()
    assert (snap.well_id, snap.well_name, snap.rig_name, snap.project_id) == (8, "SYN-W8", None, None)
    assert snap.wellbore_id is snap.section_id is snap.report_id is snap.report_date is None


def test_full_context_selection_emits_one_context_change(sel):
    wells = []
    sel.well_changed.connect(lambda *a: wells.append(a))
    sel.select_full_context(7, 5, 9, well_data=WELL, section_data={"name": "S"},
                            report_data={"report_number": 2, "report_date": "2031-07-20"},
                            wellbore_id=11, wellbore_data={"name": "B"})
    assert len(sel.events) == 1 and len(wells) == 1        # legacy signals still fire; the context once
    assert (sel.events[0].report_id, sel.events[0].wellbore_id, sel.events[0].section_id) == (9, 11, 5)
    assert sel._batch == 0


def test_batch_counter_recovers_when_a_listener_raises(sel):
    def boom(*_):
        raise RuntimeError("synthetic listener failure")
    sel.well_changed.connect(boom)
    try:
        sel.select_full_context(7, None, None, well_data=WELL)
    finally:
        sel.well_changed.disconnect(boom)
    assert sel._batch == 0
    sel.select_well(8, {"name": "SYN-W8"})
    assert sel.events[-1].well_id == 8                     # later changes still reach the tabs


def test_clear_emits_an_empty_context_and_keeps_the_period(sel):
    sel.select_period("2031-07-01", date(2031, 7, 31))
    sel.select_well(7, WELL)
    sel.clear()
    snap = sel.events[-1]
    assert snap.well_id is None and snap.well_name is None and snap.company_id is None
    assert (snap.period_from, snap.period_to) == ("2031-07-01", "2031-07-31")


def test_period_validation_and_identity(sel):
    periods = []
    sel.period_changed.connect(periods.append)
    before = sel.context_token()[0]
    with pytest.raises(ValueError, match="starts 2031-07-31 after it ends 2031-07-01"):
        sel.select_period("2031-07-31", "2031-07-01")
    with pytest.raises(ValueError, match="must be a date"):
        sel.select_period("next week", None)
    assert sel.current_period is None and sel.context_token()[0] == before and periods == []
    sel.select_period(date(2031, 7, 1), None)                # open-ended period
    assert sel.current_period == ("2031-07-01", None) and sel.context_token()[0] == before + 1
    sel.select_period(datetime(2031, 7, 1, 23, 0), None)      # same period: no signal, no new generation
    assert len(periods) == 1 and sel.context_token()[0] == before + 1
    sel.select_well(7, WELL)
    assert sel.snapshot().period_from == "2031-07-01"         # survives a well switch
    sel.select_period()
    assert sel.current_period is None and periods[-1] is None


def test_resolve_follows_the_database_relations(sel, world):
    db, ids = world
    sel.select_full_context(ids["alpha"], None, ids["report_2"],
                            well_data={"name": "payload name is not authoritative"}, report_data={})
    resolved = ctx.resolve(db, sel.snapshot())
    assert resolved["company"]["name"] == "SYNTHETIC LINK CO"
    assert resolved["project"]["name"] == "SYNTHETIC PROJECT EAST"
    assert resolved["well"]["name"] == "SYN-ALPHA-01"
    assert resolved["rig"] == {"name": "SYN RIG 1", "source": "well attribute rig_name"}
    assert resolved["report"] == {"id": ids["report_2"], "number": 2, "date": "2026-01-03"}
    assert resolved["conflicts"] == []
    assert ctx.path_text(resolved) == ("SYNTHETIC LINK CO › SYNTHETIC PROJECT EAST › SYN-ALPHA-01 (rig SYN RIG 1)"
                                       " › Report #2 2026-01-03")


def test_resolve_withholds_children_of_another_well(world):
    from core.database import Section
    db, ids = world
    with db.session_scope() as session:
        foreign_section = session.query(Section).filter(Section.well_id != ids["alpha"]).first()
        foreign_section_id = foreign_section.id if foreign_section else None
    snap = ContextSnapshot(well_id=ids["alpha"], report_id=ids["twin_report"], section_id=foreign_section_id,
                           wellbore_id=999)
    resolved = ctx.resolve(db, snap)
    assert "report" not in resolved and "wellbore" not in resolved and "section" not in resolved
    assert f"report {ids['twin_report']} is not a report of the selected well" in resolved["conflicts"]
    assert "wellbore 999 is not a wellbore of the selected well" in resolved["conflicts"]
    if foreign_section_id:
        assert f"section {foreign_section_id} is not a section of the selected well" in resolved["conflicts"]
    text = ctx.path_text(resolved)
    assert text.startswith("SYNTHETIC LINK CO › SYNTHETIC PROJECT EAST › SYN-ALPHA-01 (rig SYN RIG 1)  |  context conflict: ")
    assert "Report" not in text and f"report {ids['twin_report']} is not a report" in text


def test_resolve_reports_a_missing_well_and_never_invents_one(world):
    db, _ids = world
    resolved = ctx.resolve(db, ContextSnapshot(well_id=424242, period_from="2031-07-01"))
    assert resolved == {"conflicts": ["well 424242 does not exist"],
                        "period": {"from": "2031-07-01", "to": None}}
    assert ctx.path_text(resolved) == "No well selected"      # a conflict alone is no path


def test_resolve_without_a_database_or_selection():
    assert ctx.resolve(None, ContextSnapshot(well_id=1)) == {"conflicts": []}
    assert ctx.resolve(object(), None) == {"conflicts": []}
    assert ctx.path_text({"conflicts": []}) == "No well selected"
    assert ctx.path_text({"well": {"name": "W"}, "report": {"id": 3, "number": None, "date": None},
                          "conflicts": []}) == "W › Report id 3"
