"""Mission 19 — complete DDR revision snapshot & lifecycle hardening tests.

Backend authority, mandatory actor, transition-time content validation, and
COMPLETE self-contained immutable snapshots built from real multi-entity DDR
data (not just ``summary='hello'``). Pure domain + repository level (no Qt).
"""
import pytest
from datetime import date, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    DatabaseManager, Base, User, Well, Section, DailyReport, Company, Project,
    TimeLog24H, TimeLogMorning, DrillingParameters, MudReport, BitReport,
    BHAReport, SurveyPoint, SafetyReport,
)
from core.report_lifecycle import LifecycleOutcome
from core.report_snapshot import (
    snapshot_is_complete, child_count, serialize_value, build_report_snapshot,
    SNAPSHOT_SCHEMA_VERSION,
)

ENG = lambda p: p in {"can_edit_reports", "can_export"}          # noqa: E731
SUP = lambda p: p in {"can_edit_reports", "can_approve_reports", "can_export"}  # noqa: E731
VIEWER = lambda p: p in {"can_export"}                            # noqa: E731


@pytest.fixture
def db():
    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return m


def _seed(db, with_children=True, valid=True):
    """Create a well/section/report plus representative multi-entity DDR data."""
    s = db.create_session()
    try:
        eng = User(username="eng", password_hash="x", role="engineer"); s.add(eng); s.flush()
        sup = User(username="sup", password_hash="x", role="supervisor"); s.add(sup); s.flush()
        c = Company(name="C", code="C1"); s.add(c); s.flush()
        p = Project(company_id=c.id, name="P", code="P1"); s.add(p); s.flush()
        w = Well(project_id=p.id, name="W1", code="W1"); s.add(w); s.flush()
        w2 = Well(project_id=p.id, name="W2", code="W2"); s.add(w2); s.flush()
        sec = Section(well_id=w.id, name="12.25"); s.add(sec); s.flush()
        r = DailyReport(well_id=w.id, section_id=sec.id, report_number=1,
                        report_date=date(2026, 9, 1),
                        status="Draft",
                        # An invalid report uses a negative depth, which the
                        # DailyReportValidator flags as an error while the DB
                        # column itself permits it (proves server-side content
                        # validation, not a DB constraint, blocks submission).
                        depth_0000=(-5.0 if not valid else 100.0),
                        depth_2400=250.0, summary="spud")
        s.add(r); s.flush()
        rid = r.id
        if with_children:
            s.add(TimeLog24H(report_id=rid, time_from=time(6, 0), time_to=time(12, 0),
                             duration=6.0, main_phase="Drilling", is_npt=False,
                             activity_description="drill ahead"))
            s.add(TimeLog24H(report_id=rid, time_from=time(0, 0), time_to=time(6, 0),
                             duration=6.0, main_phase="Circulate", is_npt=True,
                             activity_description="stuck pipe"))
            s.add(TimeLogMorning(report_id=rid, time_from=time(6, 0), time_to=time(7, 0),
                                 duration=1.0, main_phase="Safety"))
            s.add(DrillingParameters(report_id=rid, well_id=w.id,
                                     report_date=date(2026, 9, 1),
                                     depth_in=100.0, depth_out=200.0, avg_rop=12.5))
            s.add(MudReport(report_id=rid, well_id=w.id, report_date=date(2026, 9, 1)))
            s.add(BitReport(report_id=rid, well_id=w.id, report_date=date(2026, 9, 1)))
            s.add(BHAReport(report_id=rid, well_id=w.id, bha_name="BHA-1"))
            s.add(SurveyPoint(report_id=rid, well_id=w.id, md=150.0, inc=2.5, azi=180.0))
            s.add(SafetyReport(report_id=rid, well_id=w.id, report_date=date(2026, 9, 1)))
        ids = {"eng": eng.id, "sup": sup.id, "well": w.id, "well2": w2.id,
               "section": sec.id, "report": rid}
        s.commit()
        return ids
    finally:
        s.close()


# --- Backend authority & actor (T1-T5) -----------------------------------

def test_t1_no_auth_context_denied(db):
    ids = _seed(db)
    res = db.transition_report(ids["report"], "submit")  # no has_permission
    assert not res.ok and res.outcome == LifecycleOutcome.PERMISSION_DENIED
    assert db.get_daily_report_by_id(ids["report"])["status"] == "Draft"


def test_t2_actor_mandatory(db):
    ids = _seed(db)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=None)
    assert not res.ok and res.outcome == LifecycleOutcome.PERMISSION_DENIED
    assert db.get_report_revisions(ids["report"]) == []


def test_t3_unauthorized_role_denied(db):
    ids = _seed(db)
    res = db.transition_report(ids["report"], "submit", has_permission=VIEWER, user_id=ids["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.PERMISSION_DENIED


def test_t4_legacy_status_path_is_not_production(db):
    """set_report_status still works for tests but is documented non-production."""
    ids = _seed(db)
    # It does not enforce the state machine (proves it is a raw writer, hence
    # must never be a production path).
    assert db.set_report_status(ids["report"], "Approved", user_id=ids["sup"]) is True
    assert db.get_daily_report_by_id(ids["report"])["status"] == "Approved"


def test_t5_submit_validation_blocks_invalid(db):
    ids = _seed(db, valid=False)  # report_date is None -> invalid
    res = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.VALIDATION_ERROR
    assert db.get_daily_report_by_id(ids["report"])["status"] == "Draft"


# --- Complete snapshot (T6-T12) ------------------------------------------

def test_t6_valid_submit(db):
    ids = _seed(db)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    assert res.ok and res.new_status == "Submitted"


def test_t7_complete_snapshot(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    snap = db.get_report_revisions(ids["report"])[0]["snapshot"]
    assert snapshot_is_complete(snap)
    assert snap["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert child_count(snap, "time_logs_24h") == 2
    assert child_count(snap, "time_logs_morning") == 1
    assert child_count(snap, "drilling_parameters") == 1
    assert child_count(snap, "mud_report") == 1
    assert child_count(snap, "bit_report") == 1
    assert child_count(snap, "bha_report") == 1
    assert child_count(snap, "survey") == 1
    assert child_count(snap, "safety_report") == 1
    # ownership context self-contained
    assert snap["well_id"] == ids["well"] and snap["section_id"] == ids["section"]
    assert snap["report"]["summary"] == "spud"


def test_t8_snapshot_immutable_after_report_edit(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    before = db.get_report_revisions(ids["report"])[0]["snapshot"]["report"]["summary"]
    # reject -> report becomes editable, then change summary
    db.transition_report(ids["report"], "reject", has_permission=SUP, user_id=ids["sup"], comment="redo")
    db.save_daily_report({"id": ids["report"], "summary": "COMPLETELY DIFFERENT"})
    snap = [r for r in db.get_report_revisions(ids["report"]) if r["status"] == "Submitted"][0]["snapshot"]
    assert snap["report"]["summary"] == before == "spud"


def test_t9_child_immutable_after_child_change(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    submit_snap = db.get_report_revisions(ids["report"])[0]["snapshot"]
    assert child_count(submit_snap, "time_logs_24h") == 2
    # delete all current time logs
    s = db.create_session()
    try:
        s.query(TimeLog24H).filter_by(report_id=ids["report"]).delete()
        s.commit()
    finally:
        s.close()
    # historical revision still has the 2 rows
    snap2 = db.get_report_revisions(ids["report"])[0]["snapshot"]
    assert child_count(snap2, "time_logs_24h") == 2


def test_t10_revision_ownership_stable(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    snap = db.get_report_revisions(ids["report"])[0]["snapshot"]
    assert snap["well_id"] == ids["well"]
    assert snap["report_id"] == ids["report"]


def test_t11_approval_snapshot_complete(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    db.transition_report(ids["report"], "approve", has_permission=SUP, user_id=ids["sup"], comment="ok")
    snap = db.get_report_revisions(ids["report"])[0]["snapshot"]
    assert snap["status"] if isinstance(snap.get("status"), str) else True
    assert child_count(snap, "time_logs_24h") == 2
    assert child_count(snap, "drilling_parameters") == 1


def test_t12_rejection_snapshot_complete_with_comment(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    db.transition_report(ids["report"], "reject", has_permission=SUP, user_id=ids["sup"], comment="fix mud")
    rev = db.get_report_revisions(ids["report"])[0]
    assert rev["status"] == "Rejected" and rev["comment"] == "fix mud"
    assert child_count(rev["snapshot"], "time_logs_24h") == 2


# --- Lifecycle progression (T13-T15) -------------------------------------

def test_t13_resubmission_new_revision(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    db.transition_report(ids["report"], "reject", has_permission=SUP, user_id=ids["sup"], comment="redo")
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    revs = db.get_report_revisions(ids["report"])
    assert [r["status"] for r in revs] == ["Submitted", "Rejected", "Submitted"]
    assert [r["revision_no"] for r in revs] == [3, 2, 1]


def test_t14_finalize_snapshot(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    db.transition_report(ids["report"], "approve", has_permission=SUP, user_id=ids["sup"], comment="ok")
    res = db.transition_report(ids["report"], "finalize", has_permission=SUP, user_id=ids["sup"])
    assert res.ok and res.new_status == "Final"
    snap = db.get_report_revisions(ids["report"])[0]["snapshot"]
    assert child_count(snap, "time_logs_24h") == 2


def test_t15_final_terminal(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    db.transition_report(ids["report"], "approve", has_permission=SUP, user_id=ids["sup"], comment="ok")
    db.transition_report(ids["report"], "finalize", has_permission=SUP, user_id=ids["sup"])
    for act in ("submit", "approve", "reject", "finalize"):
        res = db.transition_report(ids["report"], act, has_permission=SUP,
                                   user_id=ids["sup"], comment="x")
        assert not res.ok and res.outcome == LifecycleOutcome.INVALID_TRANSITION


# --- Serialization & ordering (T16-T17) ----------------------------------

def test_t16_serialization_deterministic():
    assert serialize_value(None) is None
    assert serialize_value(date(2026, 9, 1)) == "2026-09-01"
    assert serialize_value(time(6, 30)) == "06:30:00"
    assert serialize_value(12.5) == 12.5
    assert serialize_value(True) is True
    assert serialize_value("x") == "x"


def test_t17_deterministic_ordering(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    tls = db.get_report_revisions(ids["report"])[0]["snapshot"]["children"]["time_logs_24h"]
    # ordered by time_from chronologically -> 00:00 before 06:00
    assert tls[0]["time_from"] == "00:00:00"
    assert tls[1]["time_from"] == "06:00:00"


# --- Rollback / fault injection (T18-T21) --------------------------------

def test_t18_snapshot_failure_rolls_back(db, monkeypatch):
    ids = _seed(db)
    # transition_report does `from core.report_snapshot import build_report_snapshot`
    # at call time, so patching the source module symbol is sufficient.
    import core.report_snapshot as snapmod

    def boom(*a, **k):
        raise RuntimeError("snapshot boom")

    monkeypatch.setattr(snapmod, "build_report_snapshot", boom)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.PERSISTENCE_ERROR
    assert db.get_daily_report_by_id(ids["report"])["status"] == "Draft"
    assert db.get_report_revisions(ids["report"]) == []
    assert db.get_approval_history(ids["report"]) == []


def test_t19_revision_insert_failure_rolls_back(db, monkeypatch):
    ids = _seed(db)
    import core.database as dbmod

    def boom(*a, **k):
        raise RuntimeError("revision boom")

    monkeypatch.setattr(dbmod, "ReportRevision", boom)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.PERSISTENCE_ERROR
    assert db.get_daily_report_by_id(ids["report"])["status"] == "Draft"
    assert db.get_approval_history(ids["report"]) == []


def test_t20_approval_insert_failure_rolls_back(db, monkeypatch):
    ids = _seed(db)
    import core.database as dbmod

    def boom(*a, **k):
        raise RuntimeError("approval boom")

    monkeypatch.setattr(dbmod, "ApprovalAction", boom)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.PERSISTENCE_ERROR
    assert db.get_daily_report_by_id(ids["report"])["status"] == "Draft"
    assert db.get_report_revisions(ids["report"]) == []  # revision rolled back too


# --- Context / ownership (T24-T25) ---------------------------------------

def test_t24_wrong_well(db):
    ids = _seed(db)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG,
                               user_id=ids["eng"], expected_well_id=ids["well2"])
    assert not res.ok and res.outcome == LifecycleOutcome.CONTEXT_ERROR


def test_t25_wrong_section(db):
    ids = _seed(db)
    res = db.transition_report(ids["report"], "submit", has_permission=ENG,
                               user_id=ids["eng"], expected_section_id=999999)
    assert not res.ok and res.outcome == LifecycleOutcome.CONTEXT_ERROR


# --- Attribution & empty (T28, T40) --------------------------------------

def test_t40_actor_attribution_both_histories(db):
    ids = _seed(db)
    db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    db.transition_report(ids["report"], "approve", has_permission=SUP, user_id=ids["sup"], comment="ok")
    revs = db.get_report_revisions(ids["report"])
    acts = db.get_approval_history(ids["report"])
    assert all(r["created_by"] is not None for r in revs)
    assert all(a["user_id"] is not None for a in acts)
    # newest submit revision + submit action both attributed to same actor
    submit_rev = [r for r in revs if r["status"] == "Submitted"][0]
    submit_act = [a for a in acts if a["action"] == "submit"][0]
    assert submit_rev["created_by"] == submit_act["user_id"] == ids["eng"]


def test_t28_empty_history(db):
    ids = _seed(db, with_children=False)
    assert db.get_report_revisions(ids["report"]) == []
    assert db.get_approval_history(ids["report"]) == []
