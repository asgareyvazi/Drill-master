"""M124 - D7: background work and pickers bound to the central selection identity.

Real widgets, real SelectionManager, real worker threads on a temporary file SQLite database with
SYNTHETIC wells; offscreen Qt (not a Windows desktop test).  Rules under test:

* ``ContextTicket``: an immutable snapshot of the central selection plus the fields the work depends
  on and the consumer's local supersede token; a result is shown only while both are current.
* W12: the page generation includes the central identity, so a queued result of a hidden page (whose
  selection handlers are deferred) is never painted after the selection moved, and a staged paint
  stopped by a central-only change starts a new cycle.
* Trajectory comparison: a result computed for one well is neither shown nor saved after the app's
  well changed, even when the panel was not told (hidden W6 tab).
* W5 / W6 / W10 pickers select the well for the whole application, and filling a picker selects
  nothing (before M124 W5 and W6 silently switched themselves to the first well).
"""
from __future__ import annotations

import dataclasses
import gc
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import trajectory_compare as tc  # noqa: E402
from core.selection_manager import CONTEXT_FIELDS, ContextTicket, SelectionManager  # noqa: E402
from synthetic_operations import make_file_database  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sel(app):
    manager = SelectionManager()
    manager.clear()
    manager.select_period(None, None)
    yield manager
    manager.clear()
    manager.select_period(None, None)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    from core.database import Company, Project, SurveyPoint, Well
    db = make_file_database(tmp_path_factory.mktemp("m124") / "synthetic-m124.db")
    with db.session_scope() as session:
        company = Company(name="SYN Co", code="SYNC")
        session.add(company)
        session.flush()
        project = Project(name="SYN Field", code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()
        ids = {}
        for name, northing, easting in (("SYN-A", 1000.0, 2000.0), ("SYN-B", 1006.0, 2008.0)):
            well = Well(name=name, code=name, project_id=project.id, northing=northing, easting=easting,
                        rte_msl=10.0)
            session.add(well)
            session.flush()
            ids[name] = well.id
            for md in (0.0, 300.0, 600.0, 900.0):
                session.add(SurveyPoint(well_id=well.id, md=md, inc=0.0, azi=0.0))
    from core import survey_revisions as sr      # M129: well-to-well screening needs declared survey revisions
    for name in ("SYN-A", "SYN-B"):
        sr.save_revision(db, ids[name], [{"md": md, "inc": 0.0, "azi": 0.0} for md in (0.0, 300.0, 600.0, 900.0)],
                         azimuth_reference="grid", depth_datum="RKB")
    yield db, ids
    db.engine.dispose()


def _dispose(app, widget):
    """Delete now: a deleteLater() left queued is destroyed inside whatever later test flushes it."""
    from PySide6.QtCore import QCoreApplication, QEvent
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()


def _select(sel, ids, name):
    sel.select_well(ids[name], {"id": ids[name], "name": name})


# ------------------------------------------------------------------ the ticket
def test_a_ticket_follows_exactly_the_fields_it_depends_on(sel):
    sel.select_well(1, {"name": "SYN-1"})
    full = sel.ticket(local=7)
    well_only = sel.ticket(("well_id",), local=7)
    assert full.is_current(sel, 7) and well_only.is_current(sel, 7)
    steps = [(lambda: sel.select_wellbore(11, {"name": "OH"}), "wellbore"),
             (lambda: sel.select_section(21, {"name": "12 1/4"}), "section"),
             (lambda: sel.select_report(31, {"report_number": 4}), "report"),
             (lambda: sel.select_period("2026-01-01", "2026-01-31"), "period from, period to")]
    for change, words in steps:
        before = sel.ticket(local=7)
        change()
        assert before.stale_reason(sel, 7) == f"the selection changed ({words})"
        assert well_only.is_current(sel, 7), words          # a well-bound job ignores the rest
    assert full.stale_reason(sel, 8) == "superseded by a newer request"      # local token checked first
    sel.select_well(2, {"name": "SYN-2"})
    assert well_only.stale_reason(sel, 7) == "the selection changed (well)"
    sel.select_well(1, {"name": "SYN-1"})
    assert well_only.is_current(sel, 7)                      # same well again: the identity is the value
    sel.clear()
    assert not well_only.is_current(sel, 7)


def test_a_ticket_is_immutable_and_rejects_unknown_fields(sel):
    ticket = sel.ticket(("well_id", "report_id"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        ticket.local = 3                                     # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ticket.snapshot.well_id = 5                          # type: ignore[misc]
    with pytest.raises(ValueError, match="Unknown selection field"):
        sel.ticket(("rig_id",))
    assert ContextTicket(sel.snapshot()).fields == CONTEXT_FIELDS
    assert ContextTicket(sel.snapshot(), ("well_id",), 1).is_current(None, 1)   # no selection: local only
    assert sel.generation == sel.snapshot().generation


# ------------------------------------------------------------------ W12 analysis page
@pytest.fixture
def page(app, sel, world):
    from tabs.w12_Analysis import AnalysisWidget
    tab = AnalysisWidget(db_manager=world[0])
    yield tab
    tab.cleanup()
    _dispose(app, tab)


def test_a_hidden_page_sees_a_selection_change_its_handlers_have_not_run_for(page, sel, world):
    _db, ids = world
    assert not page.isVisible()
    before = page._generation
    _select(sel, ids, "SYN-A")                    # DrillTabBase defers on_well_changed for a hidden tab
    after = page._generation
    assert after[0] == before[0], "the local counter was not bumped (handler deferred)"
    assert after != before, "the central identity is part of the generation (M124)"
    page._generation += 1                         # the existing bump sites keep their meaning
    assert page._generation[0] == after[0] + 1 and page._generation[1] == after[1]
    sel.select_period("2026-01-01", "2026-01-31")
    assert page._generation[1] == after[1]        # the page does not depend on the app's period


def test_a_queued_snapshot_of_the_old_well_is_never_painted(page, sel, world, monkeypatch):
    _db, ids = world
    _select(sel, ids, "SYN-A")
    page.current_well_id = ids["SYN-A"]
    ticket = (page._generation, page._rev_seq, "before", None, 0)     # a cycle started for SYN-A
    _select(sel, ids, "SYN-B")                                         # page hidden: no local bump
    painted, restarted = [], []
    monkeypatch.setattr(page, "_paint_snapshot", lambda *a, **k: painted.append(a))
    monkeypatch.setattr(page, "update_all_data", lambda: restarted.append(page.current_well_id))
    page._on_revision(ticket, ("rev-A", {"kpi": "SYN-A values"}), None)
    assert painted == [] and restarted == [ids["SYN-B"]]              # dropped; a fresh cycle for SYN-B


def test_a_staged_paint_stopped_by_a_central_change_starts_a_new_cycle(page, sel, world, monkeypatch):
    _db, ids = world
    _select(sel, ids, "SYN-A")
    page.current_well_id = ids["SYN-A"]
    restarted = []
    monkeypatch.setattr(page, "update_all_data", lambda: restarted.append(True))
    page._rev_worker, page._paint_job = None, None
    page._snapshot_painted("rev", None, 0, None)          # failed None: the scope moved mid-paint
    assert restarted == [True]
    page._rev_worker = object()                           # a handler already started the new cycle
    page._snapshot_painted("rev", None, 0, None)
    assert restarted == [True]                            # never a second, competing cycle
    page._rev_worker = None


# ------------------------------------------------------------------ trajectory comparison
@pytest.fixture
def compare(app, sel, world):
    from tabs.trajectory_compare_panel import TrajectoryComparePanel
    db, ids = world
    _select(sel, ids, "SYN-A")
    panel = TrajectoryComparePanel(db)
    panel.set_well(ids["SYN-A"])
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("offset"))
    panel.offset_combo.setCurrentIndex(panel.offset_combo.findData(ids["SYN-B"]))
    panel.actual_combo.setCurrentIndex(1)            # M129: SYN-A's survey revision (declared references)
    panel.crs_check.setChecked(True)
    yield panel
    panel.cleanup()
    _dispose(app, panel)


def test_a_queued_comparison_is_dropped_when_the_app_well_moved(compare, sel, world):
    _db, ids = world
    compare.run()                                  # worker thread; its result is queued for the GUI
    _select(sel, ids, "SYN-B")                     # the panel is not told (its W6 host is hidden)
    assert compare.wait_until_idle()
    assert compare.result is None and compare.table.rowCount() == 0
    assert "selected well changed while comparing" in compare.status_label.text()
    assert not compare.save_button.isEnabled()


def test_the_same_comparison_is_shown_while_the_well_is_unchanged(compare, sel, world):
    _db, ids = world
    compare.run()
    sel.select_report(99, {"report_number": 9})    # report, wellbore, period: not what a comparison reads
    sel.select_period("2026-01-01", None)
    assert compare.wait_until_idle()
    assert compare.result is not None and compare.result.status == tc.ASSESSED
    assert compare.save_button.isEnabled()


def test_a_shown_comparison_is_not_saved_for_another_well(compare, sel, world):
    db, ids = world
    compare.run()
    assert compare.wait_until_idle() and compare.result is not None
    _select(sel, ids, "SYN-B")
    from core.database import TrajectoryCalculation
    with db.session_scope() as s:
        before = s.query(TrajectoryCalculation).count()
    assert compare.save() is None
    with db.session_scope() as s:
        assert s.query(TrajectoryCalculation).count() == before
    assert "nothing was saved" in compare.status_label.text() and compare.result is None


def test_two_views_drop_their_results_after_one_switch(compare, page, sel, world, monkeypatch):
    _db, ids = world
    page.current_well_id = ids["SYN-A"]
    ticket = (page._generation, page._rev_seq, "before", None, 0)
    compare.run()
    _select(sel, ids, "SYN-B")
    painted = []
    monkeypatch.setattr(page, "_paint_snapshot", lambda *a, **k: painted.append(a))
    monkeypatch.setattr(page, "update_all_data", lambda: None)
    page._on_revision(ticket, ("rev", {}), None)
    assert compare.wait_until_idle()
    assert painted == [] and compare.result is None


# ------------------------------------------------------------------ pickers
# W5/W6/W10 register themselves with module-level managers (ShortcutManager, TableManager, ...) that keep
# their Python wrappers; deleting such a tab leaves ~600 dead Qt wrappers for a later garbage collection, the
# M50 crash pattern (a later test segfaulted in gc).  In the application these tabs live for the session, so
# the tests keep them too (hidden, cleaned up), as tests/test_m44_ui.py does for W6.
_KEPT_TABS: list = []


def _retire(app, tab):
    tab.hide()
    if hasattr(tab, "cleanup"):
        tab.cleanup()
    app.processEvents()
    _KEPT_TABS.append(tab)


def _picker_tab(kind, db):
    if kind == "W6":
        from tabs.w6_Trajectory_Widget import TrajectoryWidget
        return TrajectoryWidget(db)
    if kind == "W5":
        from tabs.w5_Equipment_Widget import EquipmentWidget
        return EquipmentWidget(db_manager=db)
    from tabs.w10_Planning_Widget import PlanningWidget
    return PlanningWidget(db)


@pytest.mark.parametrize("kind", ["W6", "W5", "W10"])
def test_a_picker_selects_for_the_whole_app_and_filling_it_selects_nothing(app, sel, world, kind):
    db, ids = world
    tab = _picker_tab(kind, db)
    try:
        from PySide6.QtTest import QTest
        QTest.qWait(400)                                       # W5 fills its picker on a 200 ms timer
        assert tab.well_combo.count() >= 3                     # placeholder + SYN-A + SYN-B
        assert sel.current_well_id is None                     # building the tab selected nothing
        assert tab.well_combo.currentData() is None            # "-- Select Well --"
        tab.show()
        app.processEvents()
        tab.well_combo.setCurrentIndex(tab.well_combo.findData(ids["SYN-B"]))      # the user picks
        app.processEvents()
        assert sel.current_well_id == ids["SYN-B"]             # the app follows the picker
        assert getattr(tab, "current_well", None) == ids["SYN-B"] or tab.current_well_id == ids["SYN-B"]
        _select(sel, ids, "SYN-A")                             # and the picker follows the app
        app.processEvents()
        assert tab.well_combo.currentData() == ids["SYN-A"]
        if kind == "W6":
            assert tab.viewer_tab.well_id == ids["SYN-A"]
            assert tab.viewer_tab.compare_panel.well_id == ids["SYN-A"]
    finally:
        _retire(app, tab)


def test_a_picker_shows_the_app_well_when_built_after_the_selection(app, sel, world):
    db, ids = world
    _select(sel, ids, "SYN-B")
    tab = _picker_tab("W6", db)
    try:
        assert tab.well_combo.currentData() == ids["SYN-B"] and sel.current_well_id == ids["SYN-B"]
        tab.show()                                             # the base bootstrap loads it on first show
        app.processEvents()
        assert tab.viewer_tab.well_id == ids["SYN-B"] and tab._loaded_well_id == ids["SYN-B"]
    finally:
        _retire(app, tab)
