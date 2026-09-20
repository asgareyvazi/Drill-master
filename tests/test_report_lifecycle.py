"""Daily Drilling Report lifecycle governance tests (Mission 18).

Covers the backend-authoritative state machine, atomic persistence of
status + immutable revision + approval action, actor attribution, edit-lock by
state, permission gating by role, ownership/context integrity, and honest
empty states. These are pure domain + repository tests (no Qt).
"""
import pytest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    DatabaseManager, Base, User, Well, Section, DailyReport, Company, Project,
    ReportRevision,
)
from core.report_lifecycle import (
    decide_transition, resolve_transition, allowed_actions, is_editable,
    is_terminal, LifecycleOutcome,
)

ENG = lambda p: p in {"can_edit_reports", "can_export"}          # noqa: E731
SUP = lambda p: p in {"can_edit_reports", "can_approve_reports", "can_export"}  # noqa: E731
VIEWER = lambda p: p in {"can_export"}                            # noqa: E731


@pytest.fixture
def db():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    return manager


@pytest.fixture
def scenario(db):
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
                        report_date=date(2026, 9, 1), status="Draft"); s.add(r); s.flush()
        ids = {"eng": eng.id, "sup": sup.id, "well": w.id, "well2": w2.id,
               "section": sec.id, "report": r.id}
        s.commit()
        return ids
    finally:
        s.close()


# --- Pure domain state machine -------------------------------------------

def test_t3_invalid_submit_blocked():
    d = decide_transition("Approved", "submit", SUP)
    assert not d.ok and d.outcome == LifecycleOutcome.INVALID_TRANSITION


def test_t5_invalid_approve_from_draft():
    d = decide_transition("Draft", "approve", SUP)
    assert not d.ok and d.outcome == LifecycleOutcome.INVALID_TRANSITION


def test_domain_transition_table():
    assert resolve_transition("Draft", "submit") == "Submitted"
    assert resolve_transition("Submitted", "approve") == "Approved"
    assert resolve_transition("Submitted", "reject") == "Rejected"
    assert resolve_transition("Rejected", "submit") == "Submitted"
    assert resolve_transition("Approved", "finalize") == "Final"
    assert resolve_transition("Final", "finalize") is None
    assert allowed_actions("Final") == ()


def test_domain_editable_states():
    assert is_editable("Draft") and is_editable("Rejected")
    assert not is_editable("Submitted")
    assert not is_editable("Approved")
    assert not is_editable("Final") and is_terminal("Final")


def test_t6_reject_requires_comment():
    d = decide_transition("Submitted", "reject", SUP, comment="")
    assert not d.ok and d.outcome == LifecycleOutcome.VALIDATION_ERROR
    d2 = decide_transition("Submitted", "reject", SUP, comment="  ")
    assert not d2.ok and d2.outcome == LifecycleOutcome.VALIDATION_ERROR


# --- Repository / atomic persistence -------------------------------------

def test_t1_draft_exists(db, scenario):
    rep = db.get_daily_report_by_id(scenario["report"])
    assert rep["status"] == "Draft"


def test_t2_submit_creates_revision_action_actor(db, scenario):
    rid, uid = scenario["report"], scenario["eng"]
    res = db.transition_report(rid, "submit", has_permission=ENG, user_id=uid,
                               expected_well_id=scenario["well"],
                               expected_section_id=scenario["section"])
    assert res.ok and res.new_status == "Submitted"
    assert res.revision_id is not None and res.action_id is not None
    hist = db.get_approval_history(rid)
    assert len(hist) == 1 and hist[0]["user_id"] == uid and hist[0]["action"] == "submit"
    revs = db.get_report_revisions(rid)
    assert len(revs) == 1 and revs[0]["status"] == "Submitted" and revs[0]["created_by"] == uid


def test_t4_approve(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    res = db.transition_report(rid, "approve", has_permission=SUP,
                               user_id=scenario["sup"], comment="looks good")
    assert res.ok and res.new_status == "Approved"
    assert db.get_daily_report_by_id(rid)["status"] == "Approved"


def test_t7_valid_reject_keeps_history(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    res = db.transition_report(rid, "reject", has_permission=SUP,
                               user_id=scenario["sup"], comment="fix depths")
    assert res.ok and res.new_status == "Rejected"
    hist = db.get_approval_history(rid)
    assert [h["action"] for h in hist] == ["reject", "submit"]  # newest first


def test_t6_reject_blank_comment_backend_blocked(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    res = db.transition_report(rid, "reject", has_permission=SUP,
                               user_id=scenario["sup"], comment="   ")
    assert not res.ok and res.outcome == LifecycleOutcome.VALIDATION_ERROR
    assert db.get_daily_report_by_id(rid)["status"] == "Submitted"


def test_t8_resubmission_after_reject(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    db.transition_report(rid, "reject", has_permission=SUP, user_id=scenario["sup"], comment="redo")
    # rejected is editable again
    assert is_editable(db.get_daily_report_by_id(rid)["status"])
    res = db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    assert res.ok and res.new_status == "Submitted"
    assert len(db.get_report_revisions(rid)) == 3  # submit, reject, submit


def test_t9_edit_lock_per_state(db, scenario):
    rid = scenario["report"]
    # Draft editable
    assert db.save_daily_report({"id": rid, "summary": "draft edit"}) is not None
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    # Submitted locked
    assert db.save_daily_report({"id": rid, "summary": "should fail"}) is None
    assert db.get_daily_report_by_id(rid)["summary"] == "draft edit"


def test_t10_permission_per_role(db, scenario):
    rid = scenario["report"]
    # viewer cannot submit
    res = db.transition_report(rid, "submit", has_permission=VIEWER, user_id=scenario["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.PERMISSION_DENIED
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    # engineer cannot approve
    res = db.transition_report(rid, "approve", has_permission=ENG, user_id=scenario["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.PERMISSION_DENIED


def test_t11_user_attribution(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    db.transition_report(rid, "approve", has_permission=SUP, user_id=scenario["sup"], comment="ok")
    hist = db.get_approval_history(rid)
    assert all(h["user_id"] is not None for h in hist)
    names = db.get_usernames_by_id({scenario["eng"], scenario["sup"]})
    assert names[scenario["eng"]] == "eng" and names[scenario["sup"]] == "sup"


def test_t12_revision_immutability(db, scenario):
    rid = scenario["report"]
    db.save_daily_report({"id": rid, "summary": "first"})
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    # Mission 19: snapshot is now a complete record; the report header lives
    # under snapshot["report"].
    snap_before = db.get_report_revisions(rid)[0]["snapshot"]["report"]["summary"]
    db.transition_report(rid, "reject", has_permission=SUP, user_id=scenario["sup"], comment="no")
    db.save_daily_report({"id": rid, "summary": "second"})  # rejected -> editable
    # earliest revision snapshot unchanged despite later body edits
    revs = db.get_report_revisions(rid)
    submit_rev = [r for r in revs if r["status"] == "Submitted"][0]
    assert submit_rev["snapshot"]["report"]["summary"] == snap_before == "first"


def test_t13_atomic_failure_rollback(db, scenario):
    """If persistence of the revision/action fails, status must not change."""
    rid = scenario["report"]
    orig = db.get_daily_report_by_id(rid)["status"]
    import core.database as dbmod
    real = dbmod.ApprovalAction

    class Boom(real):
        def __init__(self, *a, **k):
            raise RuntimeError("simulated persistence failure")

    dbmod.ApprovalAction = Boom
    try:
        res = db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    finally:
        dbmod.ApprovalAction = real
    assert not res.ok and res.outcome == LifecycleOutcome.PERSISTENCE_ERROR
    assert db.get_daily_report_by_id(rid)["status"] == orig
    assert db.get_report_revisions(rid) == []  # no orphan revision committed


def test_t14_wrong_well_context(db, scenario):
    rid = scenario["report"]
    res = db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"],
                               expected_well_id=scenario["well2"])
    assert not res.ok and res.outcome == LifecycleOutcome.CONTEXT_ERROR
    assert db.get_daily_report_by_id(rid)["status"] == "Draft"


def test_t15_wrong_section_context(db, scenario):
    rid = scenario["report"]
    res = db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"],
                               expected_section_id=999999)
    assert not res.ok and res.outcome == LifecycleOutcome.CONTEXT_ERROR


def test_t16_repeat_action_no_double_state(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    # second submit is now invalid (already Submitted)
    res = db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.INVALID_TRANSITION
    assert len(db.get_report_revisions(rid)) == 1  # no duplicate revision


def test_t17_reload_state_persists(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    db.transition_report(rid, "approve", has_permission=SUP, user_id=scenario["sup"], comment="ok")
    # fresh read simulates reload
    assert db.get_daily_report_by_id(rid)["status"] == "Approved"


def test_t18_finalize_terminal(db, scenario):
    rid = scenario["report"]
    db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    db.transition_report(rid, "approve", has_permission=SUP, user_id=scenario["sup"], comment="ok")
    res = db.transition_report(rid, "finalize", has_permission=SUP, user_id=scenario["sup"])
    assert res.ok and res.new_status == "Final"
    # any further action rejected
    res2 = db.transition_report(rid, "submit", has_permission=ENG, user_id=scenario["eng"])
    assert not res2.ok and res2.outcome == LifecycleOutcome.INVALID_TRANSITION


def test_t19_not_found(db, scenario):
    res = db.transition_report(999999, "submit", has_permission=ENG, user_id=scenario["eng"])
    assert not res.ok and res.outcome == LifecycleOutcome.NOT_FOUND


def test_t20_empty_history(db, scenario):
    rid = scenario["report"]
    assert db.get_report_revisions(rid) == []
    assert db.get_approval_history(rid) == []
    assert db.get_report_revisions(888888) == []
